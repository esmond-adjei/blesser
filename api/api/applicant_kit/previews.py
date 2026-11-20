"""Thumbnail and excerpt previews for kit documents, built once and cached on disk.

Each preview is built in a child process (preview_render) with CPU, memory and
output limits, because the PDF, image and Office parsers run on member uploads.
The result is cached next to the file:

- KEY.preview1.webp: a thumbnail (images, PDFs, Office files with an embedded one)
- KEY.preview1.json: a text or table excerpt (Word, PowerPoint, Excel, CSV)
- KEY.preview1.none: no preview for this file (legacy Office formats, failures)

Bump VERSION when the renderer's output changes so old caches are rebuilt.
"""

import asyncio
import contextlib
import logging
import os
import sys
import uuid
import weakref
from pathlib import Path

logger = logging.getLogger(__name__)

VERSION = 1
SUFFIXES = (".webp", ".json", ".none")
MEDIA = {".webp": "image/webp", ".json": "application/json"}
TIMEOUT_SECONDS = 30
CONCURRENCY = 2
_slots: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(CONCURRENCY)
    return _slots[loop]


def cache_base(path: Path) -> Path:
    return path.with_name(f"{path.name}.preview{VERSION}")


def cached_files(path: Path) -> list[Path]:
    """Every preview file this document may have, across versions."""
    return [
        path.with_name(f"{path.name}.preview{version}{suffix}")
        for version in range(1, VERSION + 1)
        for suffix in SUFFIXES
    ]


def cached(path: Path) -> tuple[Path, str | None] | None:
    base = cache_base(path)
    for suffix in SUFFIXES:
        candidate = base.with_name(base.name + suffix)
        if candidate.is_file():
            return candidate, MEDIA.get(suffix)
    return None


async def _render(path: Path, content_type: str, base: Path) -> str | None:
    """Runs the renderer. Returns the media type, None for no preview, or raises TimeoutError."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "api.applicant_kit.preview_render",
        str(path),
        content_type,
        str(base),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.pathsep.join(sys.path),
        },
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        logger.info(
            "No preview for %s (%s): exit %s %s",
            path.name,
            content_type,
            process.returncode,
            err.decode(errors="replace")[-300:],
        )
        return None
    media = out.decode().strip()
    return media if media in MEDIA.values() else None


async def preview(path: Path, content_type: str) -> tuple[Path, str | None]:
    """Returns the cached preview file and its media type (None: no preview)."""
    if hit := await asyncio.to_thread(cached, path):
        return hit
    async with _semaphore():
        if hit := await asyncio.to_thread(cached, path):
            return hit
        base = cache_base(path)
        work = base.with_name(f"{base.name}.{uuid.uuid4().hex}.tmp")
        try:
            media = await _render(path, content_type, work)
        except TimeoutError:
            logger.warning("Preview timed out for %s", path.name)
            for suffix in SUFFIXES:
                with contextlib.suppress(FileNotFoundError):
                    work.with_name(work.name + suffix).unlink()
            raise
        suffix = next((s for s, m in MEDIA.items() if m == media), ".none")
        target = base.with_name(base.name + suffix)
        produced = work.with_name(work.name + suffix)
        if suffix != ".none" and not produced.is_file():
            suffix, media = ".none", None
            target = base.with_name(base.name + suffix)
        if suffix == ".none":
            await asyncio.to_thread(target.touch, 0o600)
        else:
            await asyncio.to_thread(os.replace, produced, target)
        for other in SUFFIXES:
            with contextlib.suppress(FileNotFoundError):
                work.with_name(work.name + other).unlink()
        return target, media
