"""Builds one document preview. Runs as a child process with resource limits.

Usage: python -m api.applicant_kit.preview_render SOURCE CONTENT_TYPE OUTPUT_BASE

Writes OUTPUT_BASE.webp (a thumbnail) or OUTPUT_BASE.json (a text or table
excerpt) and exits 0. Writes nothing when the format has no preview. The
parser libraries run on member uploads, so the parent process sets CPU,
memory and file size limits before this module starts.
"""

import csv
import io
import json
import os
import re
import resource
import sys
import warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree

THUMB_WIDTH = 640
THUMB_MAX_HEIGHT = 1280
MAX_IMAGE_PIXELS = 40_000_000
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_EMBEDDED_THUMB_BYTES = 2 * 1024 * 1024
TEXT_CHARS = 900
TEXT_PARAGRAPHS = 14
TABLE_ROWS = 10
TABLE_COLS = 6
CELL_CHARS = 40
CPU_SECONDS = 20
MEMORY_BYTES = 1024 * 1024 * 1024
OUTPUT_BYTES = 4 * 1024 * 1024

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IMAGES = {"image/png", "image/jpeg", "image/webp"}

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class LimitedReader(io.RawIOBase):
    """Stops a decompressing stream at a byte budget so a zip bomb can't inflate."""

    def __init__(self, raw, limit: int):
        self.raw = raw
        self.left = limit

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.left <= 0:
            return 0
        chunk = self.raw.read(min(len(buffer), self.left))
        self.left -= len(chunk)
        buffer[: len(chunk)] = chunk
        return len(chunk)


def clean(text: str, limit: int | None = None) -> str:
    text = CONTROL.sub("", text).replace("\t", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def save_thumbnail(image, out: Path) -> None:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    if image.mode == "RGBA":
        ground = Image.new("RGB", image.size, "white")
        ground.paste(image, mask=image.getchannel("A"))
        image = ground
    image.thumbnail((THUMB_WIDTH, THUMB_MAX_HEIGHT), Image.Resampling.LANCZOS)
    image.save(out, "WEBP", quality=80, method=4)


def open_image(source):
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    image = Image.open(source)
    if image.format not in {"PNG", "JPEG", "WEBP"}:
        raise ValueError(f"Unexpected image format {image.format}")
    if image.format == "JPEG":
        image.draft("RGB", (THUMB_WIDTH * 2, THUMB_MAX_HEIGHT * 2))
    image.load()
    return image


def render_pdf(source: Path, out: Path) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(source))
    try:
        page = pdf[0]
        width, height = page.get_size()
        scale = min(THUMB_WIDTH / width, THUMB_MAX_HEIGHT / height)
        bitmap = page.render(scale=scale, fill_color=(255, 255, 255, 255))
        save_thumbnail(bitmap.to_pil(), out)
    finally:
        pdf.close()


def xml_events(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as raw:
        yield from ElementTree.iterparse(
            io.BufferedReader(LimitedReader(raw, MAX_XML_BYTES)), events=("end",)
        )


def paragraphs(archive: zipfile.ZipFile, name: str, para: str, run: str) -> list[str]:
    found: list[str] = []
    parts: list[str] = []
    total = 0
    try:
        for _, node in xml_events(archive, name):
            if node.tag == run and node.text:
                parts.append(node.text)
            elif node.tag == para:
                line = clean("".join(parts))
                parts = []
                node.clear()
                if line:
                    found.append(line)
                    total += len(line)
                if total >= TEXT_CHARS or len(found) >= TEXT_PARAGRAPHS:
                    break
    except ElementTree.ParseError:
        if not found:
            raise
    return found


def embedded_thumbnail(archive: zipfile.ZipFile, out: Path) -> bool:
    for info in archive.infolist():
        name = info.filename.lower()
        if not name.startswith("docprops/thumbnail.") or not name.endswith(
            (".jpeg", ".jpg", ".png")
        ):
            continue
        if info.file_size > MAX_EMBEDDED_THUMB_BYTES:
            return False
        data = archive.read(info)
        try:
            save_thumbnail(open_image(io.BytesIO(data)), out)
        except (OSError, ValueError, SyntaxError, Warning):
            # A broken embedded thumbnail falls back to the text excerpt.
            return False
        return True
    return False


def first_slide(archive: zipfile.ZipFile) -> str | None:
    slides = [
        n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
    ]
    if not slides:
        return None
    return min(slides, key=lambda n: int(re.findall(r"\d+", n)[0]))


def first_sheet(archive: zipfile.ZipFile) -> str | None:
    sheets = [
        n for n in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
    ]
    if not sheets:
        return None
    return min(sheets, key=lambda n: int(re.findall(r"\d+", n)[0]))


def column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    if not letters:
        return -1
    index = 0
    for char in letters.group(0):
        index = index * 26 + ord(char) - 64
    return index - 1


def sheet_rows(archive: zipfile.ZipFile) -> list[list[str]]:
    sheet = first_sheet(archive)
    if not sheet:
        return []
    rows: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    cell_type = ""
    value = ""
    inline: list[str] = []
    needed: set[int] = set()
    for _, node in xml_events(archive, sheet):
        if node.tag == f"{S}v":
            value = node.text or ""
        elif node.tag == f"{S}t":
            inline.append(node.text or "")
        elif node.tag == f"{S}c":
            cell_type = node.get("t", "")
            col = column_index(node.get("r", ""))
            if 0 <= col < TABLE_COLS or (col < 0 and len(current) < TABLE_COLS):
                text = "".join(inline) if cell_type == "inlineStr" else value
                if cell_type == "s" and text.isdigit():
                    needed.add(int(text))
                padded = max(col, len(current))
                current.extend(("", "") for _ in range(padded - len(current)))
                current.append((cell_type, text))
            value, inline = "", []
            node.clear()
        elif node.tag == f"{S}row":
            if any(text for _, text in current):
                rows.append(current)
            current = []
            node.clear()
            if len(rows) >= TABLE_ROWS:
                break
    shared: dict[int, str] = {}
    if needed and "xl/sharedStrings.xml" in archive.namelist():
        index = 0
        parts: list[str] = []
        top = max(needed)
        for _, node in xml_events(archive, "xl/sharedStrings.xml"):
            if node.tag == f"{S}t":
                parts.append(node.text or "")
            elif node.tag == f"{S}si":
                if index in needed:
                    shared[index] = "".join(parts)
                parts = []
                index += 1
                node.clear()
                if index > top:
                    break
    return [
        [
            clean(
                shared.get(int(text), "") if kind == "s" and text.isdigit() else text,
                CELL_CHARS,
            )
            for kind, text in row
        ]
        for row in rows
    ]


def csv_rows(source: Path) -> list[list[str]]:
    with source.open(encoding="utf-8-sig", newline="", errors="replace") as handle:
        sample = handle.read(64 * 1024)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        handle.seek(0)
        rows = []
        for row in csv.reader(handle, dialect):
            cells = [clean(cell, CELL_CHARS) for cell in row[:TABLE_COLS]]
            if any(cells):
                rows.append(cells)
            if len(rows) >= TABLE_ROWS:
                break
        return rows


def write_json(out: Path, payload: dict) -> None:
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_table(out: Path, rows: list[list[str]]) -> bool:
    if not rows:
        return False
    width = max(len(row) for row in rows)
    write_json(
        out,
        {"type": "table", "rows": [row + [""] * (width - len(row)) for row in rows]},
    )
    return True


def render(source: Path, content_type: str, base: Path) -> str | None:
    """Writes the preview and returns its media type, or None for no preview."""
    image_out = base.with_name(base.name + ".webp")
    json_out = base.with_name(base.name + ".json")
    if content_type in IMAGES:
        save_thumbnail(open_image(source), image_out)
        return "image/webp"
    if content_type == "application/pdf":
        render_pdf(source, image_out)
        return "image/webp"
    if content_type == "text/csv":
        return "application/json" if write_table(json_out, csv_rows(source)) else None
    if content_type in {DOCX, PPTX, XLSX}:
        with zipfile.ZipFile(source) as archive:
            if embedded_thumbnail(archive, image_out):
                return "image/webp"
            if content_type == XLSX:
                return (
                    "application/json"
                    if write_table(json_out, sheet_rows(archive))
                    else None
                )
            if content_type == DOCX:
                found = paragraphs(archive, "word/document.xml", f"{W}p", f"{W}t")
            else:
                slide = first_slide(archive)
                found = paragraphs(archive, slide, f"{A}p", f"{A}t") if slide else []
            if not found:
                return None
            write_json(json_out, {"type": "text", "paragraphs": found})
            return "application/json"
    return None


def limit_resources() -> None:
    """Caps this process before any parser touches the upload."""
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_BYTES, OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def main(argv: list[str]) -> int:
    source, content_type, base = Path(argv[0]), argv[1], Path(argv[2])
    media = render(source, content_type, base)
    sys.stdout.write(media or "")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    limit_resources()
    raise SystemExit(main(sys.argv[1:]))
