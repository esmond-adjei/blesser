"""CV file storage: cv/{document_id}/original/source.{ext}, relative to the
storage root and never overwritten. Files converted from the old editor
live under cv/{document_id}/versions/.
"""

from pathlib import Path


def original_path(base: Path | str, document_id: str, ext: str = "docx") -> Path:
    return Path(base) / "cv" / document_id / "original" / f"source.{ext}"


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite stored object: {path}")
    path.write_bytes(data)


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
