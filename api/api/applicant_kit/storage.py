import csv
import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree

import magic
import olefile
from fastapi import UploadFile
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from api.applicant_kit import previews
from api.core.config import settings
from api.core.exceptions import BadRequestError, DomainError, NotFoundError
from api.core.ids import new_id

MAX_FILE_BYTES = 15 * 1024 * 1024
MEMBER_LIMIT_BYTES = 250 * 1024 * 1024
UPLOAD_REQUEST_BYTES = MAX_FILE_BYTES + 1024 * 1024
CHUNK_BYTES = 64 * 1024
# Stored files never change, so a member's browser may keep previews for a day.
PREVIEW_CACHE = "private, max-age=86400"


class UploadTooLarge(DomainError):
    status_code = 413


class UnsupportedType(DomainError):
    status_code = 415


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    content_type: str


class DocumentStorage(Protocol):
    async def save(
        self, user_id: str, upload: UploadFile, budget: int
    ) -> StoredFile: ...
    async def delete(self, key: str) -> None: ...
    async def delete_member(self, user_id: str) -> None: ...
    def download(self, key: str, filename: str, content_type: str) -> FileResponse: ...
    async def preview(self, key: str, content_type: str) -> Response: ...


def detect_type(path: Path) -> str:
    mime = magic.from_file(str(path), mime=True)
    if mime in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
        return mime
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names:
                    raise UnsupportedType(
                        "Only the listed document and image formats are supported."
                    )
                info = archive.getinfo("[Content_Types].xml")
                if info.file_size > CHUNK_BYTES or any(
                    name.lower().endswith("vbaproject.bin") for name in names
                ):
                    raise UnsupportedType(
                        "Macro-enabled Office documents are not supported."
                    )
                types = ElementTree.fromstring(archive.read(info))
                for marker, kind, main_type in (
                    (
                        "word/document.xml",
                        "wordprocessingml.document",
                        "wordprocessingml.document.main+xml",
                    ),
                    (
                        "ppt/presentation.xml",
                        "presentationml.presentation",
                        "presentationml.presentation.main+xml",
                    ),
                    (
                        "xl/workbook.xml",
                        "spreadsheetml.sheet",
                        "spreadsheetml.sheet.main+xml",
                    ),
                ):
                    expected = (
                        f"application/vnd.openxmlformats-officedocument.{main_type}"
                    )
                    declared = any(
                        node.get("PartName") == f"/{marker}"
                        and node.get("ContentType") == expected
                        for node in types
                    )
                    if marker in names and declared:
                        return f"application/vnd.openxmlformats-officedocument.{kind}"
        except (
            zipfile.BadZipFile,
            ElementTree.ParseError,
            RuntimeError,
            ValueError,
            NotImplementedError,
        ) as exc:
            raise UnsupportedType("Invalid Office document.") from exc
    if olefile.isOleFile(str(path)):
        try:
            with olefile.OleFileIO(str(path)) as document:
                for stream, kind in (
                    ("WordDocument", "application/msword"),
                    ("PowerPoint Document", "application/vnd.ms-powerpoint"),
                    ("Workbook", "application/vnd.ms-excel"),
                    ("Book", "application/vnd.ms-excel"),
                ):
                    if document.exists(stream):
                        return kind
        except (OSError, ValueError) as exc:
            raise UnsupportedType("Invalid Office document.") from exc
    if mime in {
        "text/plain",
        "text/csv",
        "application/csv",
        "text/tab-separated-values",
    }:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                sample = handle.read(CHUNK_BYTES)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                handle.seek(0)
                rows = 0
                for row in csv.reader(handle, dialect, strict=True):
                    if any(
                        ord(char) < 32 and char not in "\r\n\t"
                        for cell in row
                        for char in cell
                    ):
                        raise ValueError("Binary content")
                    rows += bool(row)
                if rows:
                    return "text/csv"
        except (UnicodeError, csv.Error, ValueError):
            pass
    raise UnsupportedType(
        "Unsupported file content. Use PDF, Office documents, CSV, PNG, JPG or WebP."
    )


class LocalDocumentStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _member_dir(self, user_id: str) -> Path:
        return self.root / hashlib.sha256(user_id.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Invalid storage key")
        return path

    async def save(self, user_id: str, upload: UploadFile, budget: int) -> StoredFile:
        directory = self._member_dir(user_id)
        await run_in_threadpool(
            directory.mkdir, parents=True, exist_ok=True, mode=0o700
        )
        path = directory / new_id()
        key = str(path.relative_to(self.root))
        size = 0
        handle = None
        try:
            fd = await run_in_threadpool(
                os.open, path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            handle = os.fdopen(fd, "wb")
            while chunk := await upload.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise UploadTooLarge("Files must be 15 MB or smaller.")
                if size > budget:
                    raise UploadTooLarge("The 250 MB storage limit would be exceeded.")
                await run_in_threadpool(handle.write, chunk)
            await run_in_threadpool(handle.close)
            handle = None
            if not size:
                raise BadRequestError("Empty files cannot be uploaded.")
            content_type = await run_in_threadpool(detect_type, path)
            return StoredFile(key, size, content_type)
        except BaseException:
            if handle:
                await run_in_threadpool(handle.close)
            await self.delete(key)
            raise

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await run_in_threadpool(path.unlink, missing_ok=True)
        for cached in previews.cached_files(path):
            await run_in_threadpool(cached.unlink, missing_ok=True)

    async def delete_member(self, user_id: str) -> None:
        directory = self._member_dir(user_id)
        if directory.exists():
            for path in directory.iterdir():
                await run_in_threadpool(path.unlink, missing_ok=True)
            await run_in_threadpool(directory.rmdir)

    def download(self, key: str, filename: str, content_type: str) -> FileResponse:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError("Document not found")
        return FileResponse(
            path,
            media_type=content_type,
            filename=filename,
            content_disposition_type="attachment",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    async def preview(self, key: str, content_type: str) -> Response:
        """A small thumbnail or excerpt of the file, for the member's own document grid."""
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError("Document not found")
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": PREVIEW_CACHE,
            "Content-Security-Policy": "default-src 'none'",
        }
        try:
            file, media = await previews.preview(path, content_type)
        except TimeoutError:
            return Response(status_code=503, headers={"Retry-After": "30"})
        if media is None:
            return Response(status_code=204, headers=headers)
        return FileResponse(file, media_type=media, headers=headers)


def get_storage() -> DocumentStorage:
    return LocalDocumentStorage(Path(settings.upload_dir))
