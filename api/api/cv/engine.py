"""DOCX upload gate and text extraction into units. Runs only in the
sandbox child (api/cv/sandbox.py), never on uploads in the API process."""

import hashlib
import io
import re
import stat
import zipfile

from lxml import etree

from api.cv import schemas as cv
from api.cv.markdown import section_hint as _section_hint

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VML_NS = "urn:schemas-microsoft-com:vml"


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _qa(tag: str) -> str:
    return f"{{{A_NS}}}{tag}"


def _qr(tag: str) -> str:
    return f"{{{R_NS}}}{tag}"


# EMF/WMF/TIFF don't render in browsers but are still extracted and served.
IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "emf": "image/x-emf",
    "wmf": "image/x-wmf",
}

_IMAGE_REF_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")


class CvEngineError(Exception):
    """Deterministic engine failure with a machine-readable code."""

    def __init__(self, message: str, code: str = "engine_error"):
        super().__init__(message)
        self.message = message
        self.code = code


# Upload limits, tuned for CVs, not archives.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000
MAX_DECOMPRESSION_RATIO = 100
MAX_SINGLE_ENTRY_BYTES = 20 * 1024 * 1024
MAX_TABLE_DEPTH = 10

_MAIN_PART = "word/document.xml"


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def validate_and_open(data: bytes, filename: str = "source.docx") -> dict[str, bytes]:
    """Security gate for every uploaded file. Returns name -> raw bytes."""
    if not data:
        raise CvEngineError("Empty file.", "empty_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CvEngineError(
            f"File too large ({len(data)} bytes, limit {MAX_UPLOAD_BYTES}).",
            "too_large",
        )
    if not data.startswith(b"PK\x03\x04"):
        raise CvEngineError(
            "Not a DOCX file (missing zip magic bytes).", "bad_magic"
        )
    lower = filename.lower()
    if lower.endswith(".docm"):
        raise CvEngineError(
            "Macro-enabled documents (.docm) are rejected.", "macro_enabled"
        )
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CvEngineError(f"Unreadable zip archive: {exc}", "bad_zip") from exc
    with zf:
        names = zf.namelist()
        if len(names) > MAX_ZIP_ENTRIES:
            raise CvEngineError("Archive has too many entries.", "too_many_entries")
        total_compressed = 0
        total_uncompressed = 0
        parts: dict[str, bytes] = {}
        for info in zf.infolist():
            name = info.filename
            if not name or name.endswith("/"):
                continue
            if name.startswith(("/", "\\")) or ".." in name.split("/"):
                raise CvEngineError(f"Unsafe archive path: {name!r}.", "path_traversal")
            if _is_symlink(info):
                raise CvEngineError(f"Symlink entries are rejected: {name!r}.", "symlink")
            if info.file_size > MAX_SINGLE_ENTRY_BYTES:
                raise CvEngineError(f"Archive entry too large: {name!r}.", "entry_too_large")
            total_compressed += info.compress_size
            total_uncompressed += info.file_size
            parts[name] = zf.read(name)
    if total_compressed > 0 and total_uncompressed / total_compressed > MAX_DECOMPRESSION_RATIO:
        raise CvEngineError("Suspicious compression ratio (possible zip bomb).", "zip_bomb")
    if "[Content_Types].xml" not in parts:
        # Encrypted Office files are an OLE envelope, not a zip of parts.
        raise CvEngineError(
            "Not an Office Open XML package (password-protected files are rejected).",
            "not_ooxml",
        )
    if _MAIN_PART not in parts:
        raise CvEngineError("Archive is not a Word document (no word/document.xml).", "no_document")
    if "word/vbaProject.bin" in parts:
        raise CvEngineError("Macro-enabled documents are rejected.", "macro_enabled")
    return parts


def _parse_xml(raw: bytes, part: str) -> etree._Element:
    if b"<!ENTITY" in raw or b"<!DOCTYPE" in raw:
        raise CvEngineError(f"DTD/entity declarations rejected in {part}.", "xxe")
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, dtd_validation=False, huge_tree=False
    )
    try:
        return etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise CvEngineError(f"Malformed XML in {part}: {exc}", "malformed_xml") from exc


#: Tabs and breaks as "\t"/"\n", so edits can't silently move text across them.
_FIXED_CHARS = {"tab": "\t", "br": "\n", "cr": "\n"}


def _in_run(el: etree._Element) -> bool:
    parent = el.getparent()
    return parent is not None and etree.QName(parent).localname == "r"


def _segments(node: etree._Element) -> list[list]:
    """[element, kind, text] per text-bearing run child: kind "t" (w:t) or
    "fixed" (w:tab / w:br / w:cr). Tab-stop definitions never count."""
    out: list[list] = []
    for el in node.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(f"{{{W_NS}}}"):
            continue
        name = etree.QName(el).localname
        if name == "t":
            out.append([el, "t", el.text or ""])
        elif name in _FIXED_CHARS and _in_run(el):
            out.append([el, "fixed", _FIXED_CHARS[name]])
    return out


def _text_of(node: etree._Element) -> str:
    return "".join(seg[2] for seg in _segments(node))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fingerprint(part: str, path: str, text: str) -> str:
    h = hashlib.sha256()
    h.update(part.encode())
    h.update(b"\x00")
    h.update(path.encode())
    h.update(b"\x00")
    h.update(_norm(text).encode())
    return h.hexdigest()[:16]


def _unit_id(part: str, path: str) -> str:
    return "u-" + hashlib.sha1(f"{part}#{path}".encode()).hexdigest()[:12]


def _style_of(p: etree._Element) -> cv.UnitStyle:
    out = cv.UnitStyle()
    pPr = p.find(_q("pPr"))
    if pPr is not None:
        jc = pPr.find(_q("jc"))
        if jc is not None and jc.get(f"{{{W_NS}}}val"):
            out.alignment = jc.get(f"{{{W_NS}}}val")
    # First run carrying explicit formatting wins for the summary.
    for r in p.iter(_q("r")):
        rPr = r.find(_q("rPr"))
        if rPr is None:
            continue
        fonts = rPr.find(_q("rFonts"))
        if fonts is not None:
            out.font_family = (
                fonts.get(f"{{{W_NS}}}ascii") or fonts.get(f"{{{W_NS}}}hAnsi")
            )
        sz = rPr.find(_q("sz"))
        if sz is not None and sz.get(f"{{{W_NS}}}val"):
            try:
                out.font_size_pt = float(sz.get(f"{{{W_NS}}}val")) / 2.0
            except ValueError:
                pass
        out.bold = rPr.find(_q("b")) is not None or out.bold
        out.italic = rPr.find(_q("i")) is not None or out.italic
        out.underline = rPr.find(_q("u")) is not None or out.underline
        color = rPr.find(_q("color"))
        if color is not None and color.get(f"{{{W_NS}}}val"):
            out.color = color.get(f"{{{W_NS}}}val")
        if out.font_family is not None:
            break
    return out


def _has(node: etree._Element, *tags: str) -> bool:
    return any(node.find(f".//{_q(t)}") is not None for t in tags)


def _read_only_reason(p: etree._Element, has_text: bool) -> str | None:
    if _has(p, "fldChar", "instrText"):
        return "complex-field: edit the source text in Word first"
    if _has(p, "ins", "del"):
        return "tracked-changes: accept or reject changes in Word first"
    for ancestor in p.iterancestors():
        if ancestor.tag == _q("sdt"):
            return "content-control: unsupported state in v1"
        if ancestor.tag in (_q("ins"), _q("del")):
            return "tracked-changes: accept or reject changes in Word first"
    if not has_text and _has(p, "drawing", "pict"):
        return "image-only: images are not text-editable in v1"
    return None


def _para_type(p: etree._Element, in_table_cell: bool, in_textbox: bool) -> str:
    pPr = p.find(_q("pPr"))
    style_val = ""
    if pPr is not None:
        pStyle = pPr.find(_q("pStyle"))
        if pPr.find(_q("numPr")) is not None:
            return "bullet"
        if pStyle is not None:
            style_val = (pStyle.get(f"{{{W_NS}}}val") or "").lower()
            if style_val.startswith("heading") or style_val == "title":
                return "heading"
            if "list" in style_val:
                return "bullet"
    if in_table_cell:
        return "table_cell"
    if in_textbox:
        return "textbox"
    # A paragraph whose visible text is one hyperlink reads as a link.
    links = p.findall(_q("hyperlink"))
    if len(links) == 1 and _norm(_text_of(links[0])) == _norm(_text_of(p)) and _norm(_text_of(p)):
        return "link"
    if not _norm(_text_of(p)) and _has(p, "drawing", "pict"):
        return "image"
    return "paragraph"


def _iter_paragraphs(root: etree._Element) -> list[tuple[etree._Element, str, bool, bool, int]]:
    """Yield (p, local_path, in_table_cell, in_textbox, table_depth) in order."""
    out: list[tuple[etree._Element, str, bool, bool, int]] = []

    def walk(node: etree._Element, prefix: str, in_cell: bool, in_box: bool, depth: int) -> None:
        if depth > MAX_TABLE_DEPTH:
            raise CvEngineError("Table nesting too deep.", "nested_too_deep")
        counters: dict[str, int] = {}
        for child in node:
            tag = etree.QName(child).localname if isinstance(child.tag, str) else ""
            if tag == "p":
                key = "p"
                counters[key] = counters.get(key, 0) + 1
                path = f"{prefix}/{key}[{counters[key]}]" if prefix else f"{key}[{counters[key]}]"
                boxes = child.findall(f".//{_q('txbxContent')}")
                if not boxes:
                    out.append((child, path, in_cell, in_box, depth))
                # A host paragraph's text lives only in its textboxes.
                for k, txbx in enumerate(boxes):
                    walk_txbx(txbx, path, k)
            elif tag == "tbl":
                counters["tbl"] = counters.get("tbl", 0) + 1
                base = f"{prefix}/tbl[{counters['tbl']}]" if prefix else f"tbl[{counters['tbl']}]"
                for ri, tr in enumerate(child.findall(_q("tr"))):
                    for ci, tc in enumerate(tr.findall(_q("tc"))):
                        cell_prefix = f"{base}/tr[{ri}]/tc[{ci}]"
                        walk(tc, cell_prefix, True, in_box, depth + 1)
            elif tag == "sdt":
                counters["sdt"] = counters.get("sdt", 0) + 1
                base = f"{prefix}/sdt[{counters['sdt']}]" if prefix else f"sdt[{counters['sdt']}]"
                content = child.find(_q("sdtContent"))
                if content is not None:
                    walk(content, base, in_cell, in_box, depth)
            elif tag in ("body", "sdtContent", "hdr", "ftr"):
                walk(child, prefix, in_cell, in_box, depth)

    def walk_txbx(txbx: etree._Element, host_path: str, k: int) -> None:
        for j, bp in enumerate(txbx.iter(_q("p"))):
            # Only direct txbxContent children have stable paths; deeper ones get their own walk.
            parent = bp.getparent()
            if parent is not txbx and not (
                parent is not None and etree.QName(parent).localname == "txbxContent"
            ):
                continue
            path = f"{host_path}/txbx[{k}]/p[{j}]"
            out.append((bp, path, False, True, 0))

    # Root may be w:document (body child), w:hdr, or w:ftr.
    body = root.find(_q("body"))
    walk(body if body is not None else root, "body" if body is not None else "", False, False, 0)
    return out


def _heading_level(p: etree._Element) -> int | None:
    """1 for the Title style, n + 1 for Heading n (so a document's
    sections sit under its title); None when the style names no level."""
    pPr = p.find(_q("pPr"))
    pStyle = pPr.find(_q("pStyle")) if pPr is not None else None
    style_val = (pStyle.get(f"{{{W_NS}}}val") or "").lower() if pStyle is not None else ""
    if style_val == "title":
        return 1
    digits = re.search(r"\d+", style_val) if style_val.startswith("heading") else None
    return min(int(digits.group()) + 1, 6) if digits else None


def _discover_text_parts(parts: dict[str, bytes]) -> list[str]:
    found = [_MAIN_PART]
    rest = [
        name
        for name in parts
        if re.fullmatch(r"word/header\d*\.xml", name) or re.fullmatch(r"word/footer\d*\.xml", name)
    ]
    # Reading order: headers before footers.
    rest.sort(key=lambda n: ("/footer" in n, n))
    return found + rest


def _image_targets(parts: dict[str, bytes], part: str) -> dict[str, str]:
    """rId -> package image path ("word/media/…") from one part's own .rels;
    {} when it has none. The same rId can differ between parts."""
    dirname, _, basename = part.rpartition("/")
    rels_name = f"{dirname}/_rels/{basename}.rels" if dirname else f"_rels/{basename}.rels"
    raw = parts.get(rels_name)
    if raw is None:
        return {}
    root = _parse_xml(raw, rels_name)
    out: dict[str, str] = {}
    for rel in root.iter():
        if etree.QName(rel).localname != "Relationship":
            continue
        rtype = rel.get("Type") or ""
        if not rtype.endswith("/image"):
            continue
        if (rel.get("TargetMode") or "").lower() == "external":
            # Remote image link: never fetch (untrusted input, no egress).
            continue
        rid = rel.get("Id")
        target = (rel.get("Target") or "").strip()
        if not rid or not target:
            continue
        if target.startswith("/"):
            # Package-root-absolute target, not part-relative.
            resolved = target.lstrip("/")
        else:
            resolved = f"{dirname}/{target}" if dirname else target
        if not resolved or ".." in resolved.split("/"):
            continue
        out[rid] = resolved
    return out


def _iter_pictures(node: etree._Element):
    """Every picture container: DrawingML drawings plus legacy VML w:pict,
    which some exporters emit with no w:drawing wrapper."""
    yield from node.iter(_q("drawing"))
    yield from node.iter(_q("pict"))


def _drawing_blip_ids(drawing: etree._Element) -> list[str]:
    """Relationship ids behind one picture: DrawingML blips plus VML imagedata."""
    ids: list[str] = []
    for blip in drawing.iter(_qa("blip")):
        rid = blip.get(_qr("embed"))
        if rid:
            ids.append(rid)
    for idata in drawing.iter(f"{{{VML_NS}}}imagedata"):
        rid = idata.get(_qr("id"))
        if rid:
            ids.append(rid)
    return ids


def _resolve_images(
    drawing: etree._Element, targets: dict[str, str], parts: dict[str, bytes]
) -> list[tuple[str, str, bytes]]:
    """(ref, media_type, bytes) per resolvable image of one picture. The ref
    is the media basename, stable because untouched entries are copied byte-for-byte."""
    resolved: list[tuple[str, str, bytes]] = []
    for rid in _drawing_blip_ids(drawing):
        target = targets.get(rid)
        if target is None:
            continue
        ref = target.rsplit("/", 1)[-1]
        if not _IMAGE_REF_RE.fullmatch(ref):
            continue
        data = parts.get(target)
        if data is None:
            continue
        ext = ref.rsplit(".", 1)[-1].lower() if "." in ref else ""
        media = IMAGE_MEDIA_TYPES.get(ext, "application/octet-stream")
        resolved.append((ref, media, data))
    return resolved


def extract_ir(parts: dict[str, bytes], version_id: str | None = None) -> cv.IrDocument:
    units: list[cv.EditableUnit] = []
    unextracted: list[str] = []
    trees: dict[str, etree._Element] = {}
    for part in _discover_text_parts(parts):
        trees[part] = _parse_xml(parts[part], part)
    block_id = "b-top"
    section_hint: str | None = None
    section_conf: float | None = None
    targets_by_part = {part: _image_targets(parts, part) for part in trees}
    for part, root in trees.items():
        short = part.split("/")[-1]
        base = short.split(".")[0]  # document, header1, footer2
        for p, local_path, in_cell, in_box, _depth in _iter_paragraphs(root):
            text = _text_of(p)
            path = local_path if part == _MAIN_PART else f"{base}/{local_path}"
            utype = _para_type(p, in_cell, in_box)
            reason = _read_only_reason(p, bool(_norm(text)))
            if utype == "heading" and not reason:
                hint, conf = _section_hint(text)
                if hint:
                    section_hint, section_conf = hint, conf
                block_id = "b-" + hashlib.sha1(f"{part}#{path}".encode()).hexdigest()[:8]
                unit_hint, unit_conf = hint, conf
            else:
                unit_hint, unit_conf = section_hint, section_conf
            image_ref: str | None = None
            image_media: str | None = None
            if utype == "image":
                # Several pictures per paragraph: the first is shown, the rest reported.
                # AlternateContent Choice + Fallback repeat the same image: dedupe by ref.
                seen: list[tuple[str, str]] = []
                for picture in _iter_pictures(p):
                    for ref, media, _data in _resolve_images(picture, targets_by_part[part], parts):
                        if all(r != ref for r, _m in seen):
                            seen.append((ref, media))
                if seen:
                    image_ref, image_media = seen[0]
                if len(seen) > 1:
                    unextracted.append(
                        f"{part}: paragraph holds {len(seen)} images; preview shows the first ({image_ref})"
                    )
            units.append(
                cv.EditableUnit(
                    id=_unit_id(part, path),
                    type=utype,  # type: ignore[arg-type]
                    text=text if _norm(text) or utype != "image" else None,
                    source=cv.UnitSource(part=part, path=path, fingerprint=_fingerprint(part, path, text)),
                    style=_style_of(p),
                    geometry=None,
                    block_id=block_id,
                    section_hint=unit_hint,
                    section_confidence=unit_conf,
                    length_budget=cv.LengthBudget(),
                    editable=reason is None,
                    read_only_reason=reason,
                    image_ref=image_ref,
                    image_media_type=image_media,
                    heading_level=_heading_level(p) if utype == "heading" else None,
                )
            )
    # Completeness: every w:t string must be covered by a unit (or reported).
    covered = "".join(u.text or "" for u in units)
    for part, root in trees.items():
        for t in root.iter(_q("t")):
            s = (t.text or "")
            if s and s not in covered and _norm(s):
                unextracted.append(f"{part}: {s[:80]!r} not mapped to a unit")
    # Pictures with no resolvable image (shapes, charts) are reported, never dropped.
    for part, root in trees.items():
        for picture in _iter_pictures(root):
            if not _resolve_images(picture, targets_by_part[part], parts):
                unextracted.append(f"{part}: drawing element (image/diagram, not extracted)")
                break
    fidelity: str = "high"
    if unextracted or any(not u.editable for u in units):
        fidelity = "medium"
    return cv.IrDocument(version_id=version_id, units=units, unextracted=unextracted, fidelity_class=fidelity)  # type: ignore[arg-type]
