"""Synthetic DOCX builder for CV editor tests: raw OOXML via zipfile + lxml, no python-docx, so fixtures stay byte-exact."""

import io
import zipfile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
V = "urn:schemas-microsoft-com:vml"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
DRAWING_TXBX = "w:txbxContent"

NSMAP_DOC = {"w": W, "r": R, "v": V}


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _t(text: str, preserve: bool = True) -> etree._Element:
    el = etree.Element(_q(W, "t"))
    el.text = text
    if preserve or text != text.strip():
        el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return el


def _run(text: str, bold: bool = False, font: str | None = None) -> etree._Element:
    r = etree.Element(_q(W, "r"))
    if bold or font:
        rPr = etree.SubElement(r, _q(W, "rPr"))
        if bold:
            etree.SubElement(rPr, _q(W, "b"))
        if font:
            rf = etree.SubElement(rPr, _q(W, "rFonts"))
            rf.set(_q(W, "ascii"), font)
            rf.set(_q(W, "hAnsi"), font)
    r.append(_t(text))
    return r


def _split_runs(text: str, font: str | None = None) -> list[etree._Element]:
    """Spell-check-style split: one sentence across several runs."""
    if len(text) < 8:
        return [_run(text, font=font)]
    cut = len(text) // 2
    return [_run(text[:cut], font=font), _run(text[cut:], font=font)]


def para(
    text: str,
    style: str | None = None,
    bullet: bool = False,
    runs: list[etree._Element] | None = None,
    align: str | None = None,
) -> etree._Element:
    p = etree.Element(_q(W, "p"))
    if style or bullet or align:
        pPr = etree.SubElement(p, _q(W, "pPr"))
        if style:
            ps = etree.SubElement(pPr, _q(W, "pStyle"))
            ps.set(_q(W, "val"), style)
        if bullet:
            numPr = etree.SubElement(pPr, _q(W, "numPr"))
            etree.SubElement(etree.SubElement(numPr, _q(W, "numId")), _q(W, "val")).set(
                _q(W, "val"), "1"
            )
        if align:
            jc = etree.SubElement(pPr, _q(W, "jc"))
            jc.set(_q(W, "val"), align)
    for r in runs if runs is not None else _split_runs(text):
        p.append(r)
    return p


def heading(text: str) -> etree._Element:
    return para(text, style="Heading1")


def hyperlink_para(text: str, url: str, rid: str) -> etree._Element:
    p = etree.Element(_q(W, "p"))
    link = etree.SubElement(p, _q(W, "hyperlink"))
    link.set(_q(R, "id"), rid)
    r = etree.SubElement(link, _q(W, "r"))
    rPr = etree.SubElement(r, _q(W, "rPr"))
    etree.SubElement(etree.SubElement(rPr, _q(W, "color")), _q(W, "val")).set(_q(W, "val"), "0563C1")
    r.append(_t(text))
    return p


def table(rows: list[list[etree._Element | str]], nested: bool = False) -> etree._Element:
    tbl = etree.Element(_q(W, "tbl"))
    etree.SubElement(tbl, _q(W, "tblPr"))
    grid = etree.SubElement(tbl, _q(W, "tblGrid"))
    width = max(len(r) for r in rows) if rows else 1
    for _ in range(width):
        gc = etree.SubElement(grid, _q(W, "gridCol"))
        gc.set(_q(W, "w"), "3000")
    for row in rows:
        tr = etree.SubElement(tbl, _q(W, "tr"))
        for cell in row:
            tc = etree.SubElement(tr, _q(W, "tc"))
            if isinstance(cell, str):
                tc.append(para(cell))
            elif cell.tag == _q(W, "tbl") and nested:
                tc.append(cell)
            else:
                tc.append(cell)
    return tbl


def textbox(text: str) -> etree._Element:
    p = etree.Element(_q(W, "p"))
    r = etree.SubElement(p, _q(W, "r"))
    pict = etree.SubElement(r, _q(W, "pict"))
    shape = etree.SubElement(pict, _q(V, "shape"))
    vbox = etree.SubElement(shape, _q(V, "textbox"))
    content = etree.SubElement(vbox, _q(W, "txbxContent"))
    content.append(para(text))
    return p


def image_para(rid: str | None = None) -> etree._Element:
    """Image paragraph; with rid the drawing carries a real a:blip link so extraction can resolve the media."""
    p = etree.Element(_q(W, "p"))
    r = etree.SubElement(p, _q(W, "r"))
    drawing = etree.SubElement(r, _q(W, "drawing"))
    inline = etree.SubElement(
        drawing, "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"
    )
    extent = etree.SubElement(
        inline, "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent"
    )
    extent.set("cx", "100000")
    extent.set("cy", "100000")
    if rid is not None:
        graphic = etree.SubElement(inline, _q(A, "graphic"))
        graphic_data = etree.SubElement(graphic, _q(A, "graphicData"))
        pic = etree.SubElement(
            graphic_data,
            "{http://schemas.openxmlformats.org/drawingml/2006/picture}pic",
        )
        blip_fill = etree.SubElement(
            pic, "{http://schemas.openxmlformats.org/drawingml/2006/picture}blipFill"
        )
        blip = etree.SubElement(blip_fill, _q(A, "blip"))
        blip.set(_q(R, "embed"), rid)
    return p


def vml_image_para(rid: str) -> etree._Element:
    """Legacy VML picture (w:pict with v:imagedata), as older Word versions emit."""
    p = etree.Element(_q(W, "p"))
    r = etree.SubElement(p, _q(W, "r"))
    pict = etree.SubElement(r, _q(W, "pict"))
    shape = etree.SubElement(pict, _q(V, "shape"))
    shape.set("style", "width:100pt;height:100pt")
    idata = etree.SubElement(shape, _q(V, "imagedata"))
    idata.set(_q(R, "id"), rid)
    return p


def compat_image_para(rid: str) -> etree._Element:
    """AlternateContent with a DrawingML Choice and VML Fallback for the same image: must count once."""
    MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    p = etree.Element(_q(W, "p"))
    r = etree.SubElement(p, _q(W, "r"))
    alt = etree.SubElement(r, _q(MC, "AlternateContent"))
    choice = etree.SubElement(alt, _q(MC, "Choice"))
    drawing = etree.SubElement(choice, _q(W, "drawing"))
    blip = etree.SubElement(drawing, _q(A, "blip"))
    blip.set(_q(R, "embed"), rid)
    fallback = etree.SubElement(alt, _q(MC, "Fallback"))
    pict = etree.SubElement(fallback, _q(W, "pict"))
    shape = etree.SubElement(pict, _q(V, "shape"))
    idata = etree.SubElement(shape, _q(V, "imagedata"))
    idata.set(_q(R, "id"), rid)
    return p


def tracked_para(text: str) -> etree._Element:
    p = para("")
    ins = etree.SubElement(p, _q(W, "ins"))
    ins.set(_q(W, "author"), "reviewer")
    r = etree.SubElement(ins, _q(W, "r"))
    r.append(_t(text))
    return p


def field_para() -> etree._Element:
    p = etree.Element(_q(W, "p"))
    for ch in ("begin", "end"):
        r = etree.SubElement(p, _q(W, "r"))
        fld = etree.SubElement(r, _q(W, "fldChar"))
        fld.set(_q(W, "fldCharType"), ch)
    return p


def sdt_para(text: str) -> etree._Element:
    sdt = etree.Element(_q(W, "sdt"))
    etree.SubElement(etree.SubElement(sdt, _q(W, "sdtPr")), _q(W, "tag"))
    content = etree.SubElement(sdt, _q(W, "sdtContent"))
    content.append(para(text))
    return sdt


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class DocxBuilder:
    def __init__(self) -> None:
        self.body: list[etree._Element] = []
        self.headers: dict[str, list[etree._Element]] = {}
        self.footers: dict[str, list[etree._Element]] = {}
        self.hyperlinks: list[tuple[str, str]] = []  # (rId, url)
        self.images = 0

    def build(self) -> bytes:
        doc = etree.Element(_q(W, "document"), nsmap=NSMAP_DOC)
        body = etree.SubElement(doc, _q(W, "body"))
        for el in self.body:
            body.append(el)
        sectPr = etree.SubElement(body, _q(W, "sectPr"))
        for i, name in enumerate(self.headers):
            ref = etree.SubElement(sectPr, _q(W, "headerReference"))
            ref.set(_q(W, "type"), "default")
            ref.set(_q(R, "id"), f"rIdH{i}")
        for i, name in enumerate(self.footers):
            ref = etree.SubElement(sectPr, _q(W, "footerReference"))
            ref.set(_q(W, "type"), "default")
            ref.set(_q(R, "id"), f"rIdF{i}")

        parts: dict[str, bytes] = {
            "[Content_Types].xml": _content_types(
                bool(self.headers), bool(self.footers), self.images
            ),
            "_rels/.rels": _rels(),
            "word/document.xml": _decl(doc),
            "word/styles.xml": _styles(),
            "word/numbering.xml": _numbering(),
            "word/_rels/document.xml.rels": _doc_rels(self),
        }
        for name, paras in {**{f"word/{k}": v for k, v in self.headers.items()},
                            **{f"word/{k}": v for k, v in self.footers.items()}}.items():
            kind = "hdr" if "/header" in name else "ftr"
            root = etree.Element(_q(W, kind), nsmap={"w": W})
            for el in paras:
                root.append(el)
            parts[name] = _decl(root)
        for i in range(self.images):
            parts[f"word/media/image{i + 1}.png"] = _TINY_PNG
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, raw in parts.items():
                zf.writestr(name, raw)
        return out.getvalue()


def _decl(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _content_types(headers: bool, footers: bool, images: int) -> bytes:
    root = etree.Element(_q(CT, "Types"), nsmap={None: CT})
    for ext, ctype in (
        ("rels", "application/vnd.openxml-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        d = etree.SubElement(root, _q(CT, "Default"))
        d.set("Extension", ext)
        d.set("ContentType", ctype)
    for part, ctype in (
        ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
        ("word/styles.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"),
        ("word/numbering.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"),
    ):
        o = etree.SubElement(root, _q(CT, "Override"))
        o.set("PartName", f"/{part}")
        o.set("ContentType", ctype)
    if images:
        d = etree.SubElement(root, _q(CT, "Default"))
        d.set("Extension", "png")
        d.set("ContentType", "image/png")
    for kind, present in (("header", headers), ("footer", footers)):
        if not present:
            continue
        o = etree.SubElement(root, _q(CT, "Override"))
        o.set("PartName", f"/word/{kind}1.xml")
        o.set(
            "ContentType",
            f"application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml",
        )
    return _decl(root)


def _rels() -> bytes:
    root = etree.Element(_q(REL, "Relationships"), nsmap={None: REL})
    rel = etree.SubElement(root, _q(REL, "Relationship"))
    rel.set("Id", "rId1")
    rel.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    )
    rel.set("Target", "word/document.xml")
    return _decl(root)


def _doc_rels(builder: DocxBuilder) -> bytes:
    root = etree.Element(_q(REL, "Relationships"), nsmap={None: REL})

    def add(rid: str, rtype: str, target: str, external: bool = False) -> None:
        rel = etree.SubElement(root, _q(REL, "Relationship"))
        rel.set("Id", rid)
        rel.set("Type", f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{rtype}")
        rel.set("Target", target)
        if external:
            rel.set("TargetMode", "External")

    n = 2
    add("rId1", "styles", "styles.xml")
    add("rId2", "numbering", "numbering.xml")
    n = 3
    for i, name in enumerate(builder.headers):
        add(f"rIdH{i}", "header", f"{name}")
        n += 1
    for i, name in enumerate(builder.footers):
        add(f"rIdF{i}", "footer", f"{name}")
        n += 1
    for i, (rid, url) in enumerate(builder.hyperlinks):
        add(rid, "hyperlink", url, external=True)
    for i in range(builder.images):
        add(f"rIdImg{i}", "image", f"media/image{i + 1}.png")
    return _decl(root)


def _styles() -> bytes:
    root = etree.Element(_q(W, "styles"), nsmap={"w": W})
    for style_id, name in (("Normal", "Normal"), ("Heading1", "heading 1")):
        st = etree.SubElement(root, _q(W, "style"))
        st.set(_q(W, "type"), "paragraph")
        st.set(_q(W, "styleId"), style_id)
        nm = etree.SubElement(st, _q(W, "name"))
        nm.set(_q(W, "val"), name)
    return _decl(root)


def _numbering() -> bytes:
    root = etree.Element(_q(W, "numbering"), nsmap={"w": W})
    abstract = etree.SubElement(root, _q(W, "abstractNum"))
    abstract.set(_q(W, "abstractNumId"), "0")
    etree.SubElement(abstract, _q(W, "lvl"))
    num = etree.SubElement(root, _q(W, "num"))
    num.set(_q(W, "numId"), "1")
    abs_id = etree.SubElement(num, _q(W, "abstractNumId"))
    abs_id.set(_q(W, "val"), "0")
    return _decl(root)


def corpus_simple() -> bytes:
    b = DocxBuilder()
    b.body = [heading("Jane Doe"), para("Research assistant in robotics."),
              heading("Experience"), para("Lab tech, 2023-2025.", bullet=True)]
    return b.build()


def corpus_tables() -> bytes:
    inner = table([[para("nested a"), para("nested b")]])
    b = DocxBuilder()
    b.body = [heading("Education"),
              table([[heading("Degree"), para("PhD, Robotics")],
                     ["MSc, 2020", inner]], nested=True)]
    return b.build()


def corpus_rich() -> bytes:
    b = DocxBuilder()
    b.hyperlinks.append(("rIdHyp0", "https://example.com/paper"))
    b.images = 1
    b.headers = {"header1.xml": [para("Jane Doe — CV")] }
    b.footers = {"footer1.xml": [para("page", align="center")]}
    b.body = [heading("Summary"), para("Mobile robotics and reinforcement learning."),
              hyperlink_para("Best paper (example.com)", "https://example.com/paper", "rIdHyp0"),
              textbox("Open to relocation."), image_para("rIdImg0")]
    return b.build()


def corpus_guarded() -> bytes:
    b = DocxBuilder()
    b.body = [heading("Experience"), tracked_para("Unreviewed insertion."),
              field_para(), sdt_para("Controlled block.")]
    return b.build()


def corpus_long() -> bytes:
    b = DocxBuilder()
    body: list[etree._Element] = [heading("Publications")]
    for i in range(25):
        body.append(para(f"Paper {i}: reinforcement learning for navigation.", bullet=True))
    body.append(heading("Teaching"))
    body.append(table([[f"Course {i}", "TA"] for i in range(5)]))
    b.body = body
    return b.build()


def all_corpus() -> dict[str, bytes]:
    return {
        "simple": corpus_simple(),
        "tables": corpus_tables(),
        "rich": corpus_rich(),
        "guarded": corpus_guarded(),
        "long": corpus_long(),
    }
