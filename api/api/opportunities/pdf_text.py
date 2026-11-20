"""Text from PDF calls for applications.

Many Ghana government and university calls are only published as PDFs. A PDF
is untrusted input from the open web, so it is parsed in a separate Python
process with a memory cap, a CPU cap, no file writes and a wall-clock timeout.
A malformed, oversized or hostile file costs that child process, never the
worker. The result is a plain `Page`, so triage, extraction and save grounding
treat PDF text exactly like HTML text.

Run as a script, this module is the child: it reads PDF bytes on stdin and
writes one JSON object on stdout. It must import nothing from `api`, because
the child starts with `python -I`, which leaves the project off `sys.path`.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass

# Errors are stable codes, stored on the cached page and used as triage reasons.
TOO_LARGE = "pdf_too_large"
ENCRYPTED = "pdf_encrypted"
UNREADABLE = "pdf_unreadable"
NO_TEXT = "pdf_no_text"
TIMEOUT = "pdf_timeout"

# Below this many characters a PDF is a scan or a form, not a readable call.
MIN_TEXT_CHARS = 120
MAX_LINKS = 40
PDF_TYPES = {"application/pdf", "application/x-pdf", "application/acrobat"}
_GENERIC_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "application/force-download",
    "application/download",
}


@dataclass
class PdfBody:
    """Raw PDF bytes from a fetch; `truncated` means the size cap was hit."""

    data: bytes
    truncated: bool = False


def declared_pdf(content_type: str, path: str) -> bool:
    """True when headers or the URL say the response is a PDF."""
    kind = content_type.split(";", 1)[0].strip().lower()
    return kind in PDF_TYPES or (
        kind in _GENERIC_TYPES and path.lower().rstrip("/").endswith(".pdf")
    )


def has_pdf_magic(data: bytes) -> bool:
    # The spec allows junk before the header; readers look in the first 1 KB.
    return b"%PDF-" in data[:1024]


def _limit_resources(memory_mb: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:  # not POSIX; the wall-clock timeout still applies
        return
    limits = [
        (resource.RLIMIT_CPU, cpu_seconds),
        (resource.RLIMIT_FSIZE, 0),
        (resource.RLIMIT_AS, memory_mb * 1024 * 1024),
    ]
    for name, value in limits:
        try:
            resource.setrlimit(name, (value, value))
        except (ValueError, OSError):
            pass  # some platforms (macOS) refuse RLIMIT_AS


def _links(page) -> list[str]:
    found = []
    for annot in page.get("/Annots") or []:
        try:
            action = annot.get_object().get("/A") or {}
            uri = action.get_object().get("/URI") if action else None
        except Exception:  # noqa: BLE001, S112 - one bad annotation must not end the read
            continue
        if isinstance(uri, bytes):
            uri = uri.decode("latin-1")
        if isinstance(uri, str) and uri.lower().startswith(("http://", "https://")):
            found.append(uri.strip()[:500])
    return found


def extract(data: bytes, *, max_pages: int, max_chars: int) -> dict:
    """Parse PDF bytes into {title, text, links, pages} or {error}."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            # Owner-locked PDFs open with an empty user password; others cannot.
            try:
                if not reader.decrypt(""):
                    return {"error": ENCRYPTED}
            except (PyPdfError, NotImplementedError, ValueError):
                return {"error": ENCRYPTED}
        title = ""
        try:
            title = str((reader.metadata or {}).get("/Title") or "").strip()
        except (PyPdfError, ValueError, TypeError):
            pass
        parts, links, size = [], [], 0
        pages = len(reader.pages)
        for page in reader.pages[:max_pages]:
            try:
                chunk = page.extract_text() or ""
            except (PyPdfError, ValueError, TypeError, KeyError):
                chunk = ""
            parts.append(chunk)
            size += len(chunk)
            if len(links) < MAX_LINKS:
                links.extend(_links(page))
            if size >= max_chars:
                break
    except (PyPdfError, ValueError, TypeError, KeyError, RecursionError):
        return {"error": UNREADABLE}
    return {
        "title": " ".join(title.split())[:300],
        "text": "\n\n".join(parts)[:max_chars],
        "links": list(dict.fromkeys(links))[:MAX_LINKS],
        "pages": pages,
    }


def _child() -> None:
    max_pages, max_chars, memory_mb, cpu_seconds = (int(a) for a in sys.argv[1:5])
    data = sys.stdin.buffer.read()
    _limit_resources(memory_mb, cpu_seconds)
    try:
        result = extract(data, max_pages=max_pages, max_chars=max_chars)
    except MemoryError:
        result = {"error": TOO_LARGE}
    except Exception:  # noqa: BLE001 - any parser crash is an unreadable file
        result = {"error": UNREADABLE}
    sys.stdout.buffer.write(json.dumps(result).encode())


_SEM: asyncio.Semaphore | None = None


def _sem(limit: int) -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(max(1, limit))
    return _SEM


async def run_child(data: bytes, settings) -> dict:
    """Run `extract` in a resource-limited child; never raises for bad input."""
    async with _sem(settings.pdf_concurrency):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            os.path.abspath(__file__),
            str(settings.pdf_max_pages),
            str(settings.pdf_max_chars),
            str(settings.pdf_memory_mb),
            str(max(1, int(settings.pdf_timeout_seconds))),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={"LC_ALL": "C.UTF-8"},
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(data), timeout=settings.pdf_timeout_seconds
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {"error": TIMEOUT}
    if proc.returncode != 0:
        # Killed by the CPU or memory limit, or the interpreter itself failed.
        return {"error": UNREADABLE}
    try:
        result = json.loads(out)
    except ValueError:
        return {"error": UNREADABLE}
    return result if isinstance(result, dict) else {"error": UNREADABLE}


async def read_pdf(body: PdfBody, url: str):
    """A `Page` for a fetched PDF, or one carrying a `pdf_*` error code."""
    from api.core.config import settings
    from api.opportunities.page_content import Page

    if body.truncated or len(body.data) > settings.pdf_max_bytes:
        return Page(url=url, error=TOO_LARGE)
    if not has_pdf_magic(body.data):
        return Page(url=url, error=UNREADABLE)
    result = await run_child(body.data, settings)
    if result.get("error"):
        return Page(url=url, error=str(result["error"])[:60])
    body_text = str(result.get("text") or "")
    if len(body_text.strip()) < MIN_TEXT_CHARS:
        return Page(url=url, error=NO_TEXT)
    title = str(result.get("title") or "")
    if not title:
        title = next(
            (line.strip() for line in body_text.splitlines() if line.strip()), ""
        )
    title = title[:300]
    text = title + "\n" + body_text
    links = [link for link in result.get("links") or [] if isinstance(link, str)]
    if links:
        text += "\nLinks in this PDF:\n" + "\n".join(links)
    text = text[: settings.pdf_max_chars]
    return Page(
        url=url,
        text=text,
        title=title,
        metadata={
            "deadlines": [],
            "structured": [],
            # Links stay in the text for the extractor; PDFs never expand into
            # more candidates.
            "links": [],
            "format": "pdf",
            "pdf_pages": int(result.get("pages") or 0),
        },
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


if __name__ == "__main__":
    _child()
