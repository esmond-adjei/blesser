"""PDF text extraction for CV uploads. Runs only in the sandbox child:
untrusted PDFs are never parsed in the API process."""

import io

from api.cv.engine import MAX_UPLOAD_BYTES, CvEngineError

MAX_PAGES = 30


def extract_pages(data: bytes) -> list[str]:
    """The text of each page, in order. Rejects what isn't a readable,
    unencrypted PDF, and scans with no text layer."""
    if not data:
        raise CvEngineError("Empty file.", "empty_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CvEngineError(
            f"File too large ({len(data)} bytes, limit {MAX_UPLOAD_BYTES}).", "too_large"
        )
    if not data.lstrip()[:5] == b"%PDF-":
        raise CvEngineError("Not a PDF file (missing %PDF header).", "bad_magic")
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise CvEngineError("Password-protected PDFs are rejected.", "encrypted")
        if len(reader.pages) > MAX_PAGES:
            raise CvEngineError(
                f"This PDF has {len(reader.pages)} pages; a CV should have at most {MAX_PAGES}.",
                "too_many_pages",
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except CvEngineError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise CvEngineError(f"Unreadable PDF: {exc}", "bad_pdf") from exc
    if not any(p.strip() for p in pages):
        raise CvEngineError(
            "This PDF has no text to read (it may be a scan). Upload the "
            "DOCX, or a PDF exported from your word processor.",
            "no_text",
        )
    return pages
