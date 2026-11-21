"""Reads the text of a member's CV. Runs as a child process with resource limits.

Usage: python -m api.applicant_kit.cv_text SOURCE CONTENT_TYPE

Writes one JSON object on stdout: {"text": ..., "links": [...]} or
{"error": code}. The parsers run on member uploads, so this process caps its
own CPU, memory and file writes before touching the file, like the preview
renderer. Nothing here logs or writes the text anywhere but stdout.
"""

import json
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from api.applicant_kit.preview_render import DOCX, clean, limit_resources, xml_events
from api.opportunities.pdf_text import extract as pdf_extract

MAX_CHARS = 30_000
MAX_PAGES = 8
MAX_LINKS = 40
PDF = "application/pdf"
TYPES = frozenset({PDF, DOCX})

NO_TEXT = "no_text"
UNREADABLE = "unreadable"
ENCRYPTED = "encrypted"
UNSUPPORTED = "unsupported"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
HYPERLINK = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
)


def docx_text(source: Path) -> dict:
    lines: list[str] = []
    parts: list[str] = []
    size = 0
    with zipfile.ZipFile(source) as archive:
        try:
            for _, node in xml_events(archive, "word/document.xml"):
                if node.tag == f"{W}t" and node.text:
                    parts.append(node.text)
                elif node.tag == f"{W}tab":
                    parts.append(" ")
                elif node.tag == f"{W}p":
                    line = clean("".join(parts))
                    parts = []
                    node.clear()
                    if line:
                        lines.append(line)
                        size += len(line) + 1
                    if size >= MAX_CHARS:
                        break
        except ElementTree.ParseError:
            if not lines:
                raise
        links: list[str] = []
        rels = "word/_rels/document.xml.rels"
        if rels in archive.namelist():
            for _, node in xml_events(archive, rels):
                target = node.get("Target", "")
                if (
                    node.tag == f"{RELS}Relationship"
                    and node.get("Type") == HYPERLINK
                    and target.lower().startswith(("http://", "https://", "mailto:"))
                ):
                    links.append(target.strip()[:500])
                if len(links) >= MAX_LINKS:
                    break
    return {"text": "\n".join(lines)[:MAX_CHARS], "links": links}


def read(source: Path, content_type: str) -> dict:
    if content_type == PDF:
        result = pdf_extract(
            source.read_bytes(), max_pages=MAX_PAGES, max_chars=MAX_CHARS
        )
        if error := result.get("error"):
            return {"error": ENCRYPTED if error.endswith("encrypted") else UNREADABLE}
        result = {"text": result["text"], "links": result.get("links", [])}
    elif content_type == DOCX:
        result = docx_text(source)
    else:
        return {"error": UNSUPPORTED}
    text = re.sub(r"[ \t]+", " ", result["text"]).strip()
    # Under this many letters the file is a scan, a photo or a blank template.
    if sum(char.isalpha() for char in text) < 80:
        return {"error": NO_TEXT}
    links = [link for link in dict.fromkeys(result["links"]) if link][:MAX_LINKS]
    return {"text": text, "links": links}


def main(argv: list[str]) -> int:
    source, content_type = Path(argv[0]), argv[1]
    try:
        result = read(source, content_type)
    except MemoryError:
        result = {"error": UNREADABLE}
    except Exception:  # noqa: BLE001 - any parser crash is an unreadable file
        result = {"error": UNREADABLE}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    limit_resources()
    raise SystemExit(main(sys.argv[1:]))
