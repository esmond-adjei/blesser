import io
import zipfile

import pytest

from api.cv import engine
from api.cv import schemas as cv
from tests.cv_fixtures import DocxBuilder, all_corpus, corpus_rich, image_para, para


def _ir(data: bytes) -> cv.IrDocument:
    return engine.extract_ir(engine.validate_and_open(data))


def _repack(data: bytes, mutate) -> bytes:
    parts = engine.validate_and_open(data)
    mutate(parts)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, raw in parts.items():
            zf.writestr(name, raw)
    return out.getvalue()


def test_extraction_completeness():
    from lxml import etree

    for name, data in all_corpus().items():
        parts = engine.validate_and_open(data)
        ir = engine.extract_ir(parts)
        covered = "".join(u.text or "" for u in ir.units)
        reported = " ".join(ir.unextracted)
        for part in ("word/document.xml",):
            root = etree.fromstring(parts[part])
            for t in root.iter(f"{{{engine.W_NS}}}t"):
                s = t.text or ""
                if not s.strip():
                    continue
                assert s in covered or s[:40] in reported, (name, part, s[:60])


def test_security_failures_are_safe():
    data = all_corpus()["simple"]
    # XXE payload (rejected at XML parse time).
    evil = _repack(data, lambda p: p.update(
        {"word/document.xml": p["word/document.xml"].replace(
            b"<w:document", b'<!DOCTYPE x [<!ENTITY xxe "evil">]><w:document', 1)}))
    with pytest.raises(engine.CvEngineError):
        engine.extract_ir(engine.validate_and_open(evil))
    # Path traversal entry.
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("../../evil.xml", b"<x/>")
        zf.writestr("[Content_Types].xml", b"<x/>")
        zf.writestr("word/document.xml", b"<x/>")
    with pytest.raises(engine.CvEngineError):
        engine.validate_and_open(out.getvalue())
    # Oversized file.
    with pytest.raises(engine.CvEngineError):
        engine.validate_and_open(b"PK\x03\x04" + b"x" * (engine.MAX_UPLOAD_BYTES + 1))
    # Bad magic.
    with pytest.raises(engine.CvEngineError):
        engine.validate_and_open(b"%PDF-1.4 fake")
    # Macro-enabled.
    macro = _repack(data, lambda p: p.update({"word/vbaProject.bin": b"macro"}))
    with pytest.raises(engine.CvEngineError):
        engine.validate_and_open(macro, "cv.docm")
    # Malformed XML (rejected at XML parse time).
    broken = _repack(data, lambda p: p.update({"word/document.xml": b"<w:document broken"}))
    with pytest.raises(engine.CvEngineError):
        engine.extract_ir(engine.validate_and_open(broken))
    # Symlink entry.
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in ("[Content_Types].xml", "word/document.xml"):
            zf.writestr(name, b"<x/>")
        info = zipfile.ZipInfo("word/link.xml")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, b"target")
    with pytest.raises(engine.CvEngineError):
        engine.validate_and_open(out.getvalue())


def test_image_units_carry_refs():
    parts = engine.validate_and_open(corpus_rich())
    ir = engine.extract_ir(parts)
    images = [u for u in ir.units if u.type == "image"]
    assert len(images) == 1
    assert images[0].image_ref == "image1.png"
    assert images[0].image_media_type == "image/png"
    assert not images[0].editable


def test_unlinked_drawing_stays_placeholder():
    b = DocxBuilder()
    b.images = 1  # media + rels exist, but no blip links to them
    b.body = [para("Hello"), image_para()]
    ir = engine.extract_ir(engine.validate_and_open(b.build()))
    images = [u for u in ir.units if u.type == "image"]
    assert len(images) == 1
    assert images[0].image_ref is None
    assert any("drawing element" in note for note in ir.unextracted)


def test_vml_pict_image_resolves():
    from tests.cv_fixtures import vml_image_para

    b = DocxBuilder()
    b.images = 1
    b.body = [para("Hello"), vml_image_para("rIdImg0")]
    ir = engine.extract_ir(engine.validate_and_open(b.build()))
    images = [u for u in ir.units if u.type == "image"]
    assert len(images) == 1
    assert images[0].image_ref == "image1.png"
    assert images[0].image_media_type == "image/png"
    assert not any("drawing element" in note for note in ir.unextracted)


def test_compat_markup_image_counts_once():
    from tests.cv_fixtures import compat_image_para

    b = DocxBuilder()
    b.images = 1
    b.body = [para("Hello"), compat_image_para("rIdImg0")]
    ir = engine.extract_ir(engine.validate_and_open(b.build()))
    images = [u for u in ir.units if u.type == "image"]
    assert len(images) == 1
    assert images[0].image_ref == "image1.png"
    assert not any("holds 2 images" in note for note in ir.unextracted)


def test_image_targets_absolute_and_external():
    import io
    import zipfile

    from tests.cv_fixtures import DocxBuilder, image_para, para

    b = DocxBuilder()
    b.images = 1
    b.body = [para("Hello"), image_para("rIdAbs")]
    data = b.build()

    # Rewrite the image rel: absolute package path + an external decoy.
    from lxml import etree

    REL = "http://schemas.openxmlformats.org/package/2006/relationships"
    buf = io.BytesIO(data)
    zin = zipfile.ZipFile(buf)
    parts = {n: zin.read(n) for n in zin.namelist()}
    root = etree.fromstring(parts["word/_rels/document.xml.rels"])
    for rel in root.iter(f"{{{REL}}}Relationship"):
        if rel.get("Id") == "rIdImg0":
            rel.set("Id", "rIdAbs")
            rel.set("Target", "/word/media/image1.png")
    ext = etree.SubElement(root, f"{{{REL}}}Relationship")
    ext.set("Id", "rIdExt")
    ext.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )
    ext.set("Target", "https://example.com/evil.png")
    ext.set("TargetMode", "External")
    parts["word/_rels/document.xml.rels"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, raw in parts.items():
            zf.writestr(name, raw)

    # Nothing renders a CV any more, so an external link is never fetched
    # and doesn't block the upload; the absolute target resolves.
    ir = engine.extract_ir(engine.validate_and_open(out.getvalue()))
    images = [u for u in ir.units if u.type == "image"]
    assert len(images) == 1
    assert images[0].image_ref == "image1.png"


def test_heading_levels_follow_the_style():
    b = DocxBuilder()
    b.body = [para("Jane Doe", style="Title"), para("Education", style="Heading1"), para("PhD", style="Heading2")]
    ir = _ir(b.build())
    levels = {u.text: u.heading_level for u in ir.units if u.type == "heading"}
    assert levels == {"Jane Doe": 1, "Education": 2, "PhD": 3}
