"""Read uploaded CVs outside the API process.

Each parse runs in a short-lived child (sandbox_worker.py) with a scrubbed
environment (no secrets), resource limits, a wall-clock timeout that kills
its process group, no network where unprivileged network namespaces are
allowed, and JSON-only I/O. Bad input raises CvEngineError (400); a limit
or the timeout raises SandboxLimitError (422).

CV_SANDBOX=inline runs the same code in-process (debugging only).
"""

import asyncio
import base64
import json
import logging
import os
import resource
import shutil
import signal
import sys
import tempfile
from pathlib import Path

from api.core.config import settings
from api.cv import engine
from api.cv import schemas as cv

log = logging.getLogger(__name__)

LIMITS = {
    "parse": {"mem_mb": 1024, "cpu_s": 30, "wall_s": 45},
}
MAX_OUTPUT_FILE_MB = 200
_API_ROOT = Path(__file__).resolve().parents[2]
_NETNS: bool | None = None


class SandboxLimitError(Exception):
    """The job hit a resource limit or the timeout and was killed."""

    def __init__(self, message: str, code: str = "limit"):
        super().__init__(message)
        self.message = message
        self.code = code


def _netns_available() -> bool:
    global _NETNS
    if _NETNS is None:
        exe = shutil.which("unshare")
        _NETNS = False
        if exe and sys.platform.startswith("linux"):
            import subprocess

            try:
                _NETNS = (
                    subprocess.run(
                        [exe, "--user", "--net", "--map-root-user", "true"],
                        capture_output=True,
                        check=False,
                        timeout=5,
                    ).returncode
                    == 0
                )
            except Exception:  # noqa: BLE001 - probe only
                _NETNS = False
    return _NETNS


#: Unprivileged account the child runs as when the API runs as root (api/Dockerfile).
SANDBOX_USER = "cvsandbox"


def _child_identity() -> tuple[int, int] | None:
    """(uid, gid) to drop to, or None when already unprivileged or the
    sandbox account doesn't exist (local development)."""
    if os.geteuid() != 0:
        return None
    try:
        import pwd

        entry = pwd.getpwnam(SANDBOX_USER)
    except (ImportError, KeyError):
        return None
    return entry.pw_uid, entry.pw_gid


def sandbox_status() -> dict:
    return {
        "mode": settings.cv_sandbox,
        "network_isolated": settings.cv_sandbox == "process" and _netns_available(),
        "unprivileged": settings.cv_sandbox == "process"
        and (os.geteuid() != 0 or _child_identity() is not None),
        "limits": LIMITS,
    }


def _child_env(home: str) -> dict:
    """Only what Python needs; secrets never cross over."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": home,
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(_API_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    return env


def _limits(kind: str):
    lim = LIMITS[kind]

    def apply() -> None:  # runs in the child between fork and exec
        mem = lim["mem_mb"] * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (lim["cpu_s"], lim["cpu_s"] + 5))
        fsize = MAX_OUTPUT_FILE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def _raise_child_error(err: dict):
    if err["kind"] == "engine":
        raise engine.CvEngineError(err["message"], err["code"])
    raise SandboxLimitError(
        "This document is too large or complex to process safely.",
        err.get("code", "limit"),
    )


async def _run_process(req: dict, kind: str) -> dict:
    lim = LIMITS[kind]
    payload = json.dumps(req).encode()
    with tempfile.TemporaryDirectory(prefix="cv-sandbox-") as home:
        # -I: isolated mode (ignores PYTHON* env and user site-packages), so
        # the package root is put on sys.path explicitly.
        boot = (
            f"import sys; sys.path.insert(0, {str(_API_ROOT)!r}); import runpy; "
            "runpy.run_module('api.cv.sandbox_worker', run_name='__main__')"
        )
        cmd = [sys.executable, "-I", "-c", boot]
        if _netns_available():
            cmd = [shutil.which("unshare"), "--user", "--net", "--map-root-user", *cmd]
        identity = _child_identity()
        drop: dict = {}
        if identity is not None:
            # Root API (the Docker image): run the child as the sandbox account.
            os.chown(home, *identity)
            drop = {"user": identity[0], "group": identity[1], "extra_groups": []}
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=home,
            env=_child_env(home),
            preexec_fn=_limits(kind),
            start_new_session=True,
            **drop,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(payload), timeout=lim["wall_s"]
            )
        except TimeoutError:
            _kill_group(proc.pid)
            await proc.wait()
            raise SandboxLimitError(
                "This document took too long to process and was stopped.", "timeout"
            ) from None
        finally:
            _kill_group(proc.pid)  # reap anything the child left running
    if proc.returncode != 0 or not out:
        reason = (
            "cpu" if proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL) else "crash"
        )
        log.warning(
            "cv sandbox %s exited %s: %s", req.get("op"), proc.returncode, err[-500:]
        )
        raise SandboxLimitError(
            "This document is too large or complex to process safely.", reason
        )
    try:
        reply = json.loads(out)
    except json.JSONDecodeError as exc:
        raise SandboxLimitError(
            "The document processor returned garbage.", "protocol"
        ) from exc
    if "error" in reply:
        _raise_child_error(reply["error"])
    return reply["ok"]


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


async def _run(req: dict, kind: str) -> dict:
    if settings.cv_sandbox == "inline":
        from api.cv import sandbox_worker

        try:
            return await asyncio.to_thread(sandbox_worker.handle, req)
        except MemoryError as exc:  # pragma: no cover - inline debugging only
            raise SandboxLimitError("out of memory", "memory") from exc
    return await _run_process(req, kind)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


async def extract_docx(data: bytes, filename: str) -> cv.IrDocument:
    """Validate a DOCX upload and read its text units, in the sandbox."""
    out = await _run(
        {"op": "docx", "data": _b64(data), "filename": filename}, "parse"
    )
    return cv.IrDocument.model_validate(out["ir"])


async def extract_pdf(data: bytes) -> list[str]:
    """Validate a PDF upload and read its text per page, in the sandbox."""
    out = await _run({"op": "pdf", "data": _b64(data)}, "parse")
    return list(out["pages"])
