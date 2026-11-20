import io
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from api.applicant_kit import models, preview_render, previews
from tests.test_applicant_kit import PDF, kit, rows, upload  # noqa: F401

pytestmark = pytest.mark.real_auth

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def image_bytes(size=(1600, 900), fmt="PNG", exif=None):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (200, 40, 40))
    if exif:
        image.save(buffer, fmt, exif=exif)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()


def pdf_bytes(width=595, height=842):
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width, height)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


def office(main: str, main_type: str, parts: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'<Types><Override PartName="/{main}" ContentType="application/vnd.openxmlformats-officedocument.{main_type}"/></Types>',
        )
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{text[:5]}</w:t></w:r><w:r><w:t>{text[5:]}</w:t></w:r></w:p>"
        for text in paragraphs
    )
    return office(
        "word/document.xml",
        "wordprocessingml.document.main+xml",
        {
            "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
        },
    )


def xlsx() -> bytes:
    sheet = (
        f'<worksheet xmlns="{S}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Laptop</t></is></c><c r="C2"><v>4200</v></c>'
        '<c r="Z2"><v>99</v></c></row>'
        "</sheetData></worksheet>"
    )
    shared = f'<sst xmlns="{S}"><si><t>Item</t></si><si><r><t>Cost </t></r><r><t>(GHS)</t></r></si></sst>'
    return office(
        "xl/workbook.xml",
        "spreadsheetml.sheet.main+xml",
        {
            "xl/workbook.xml": "<workbook/>",
            "xl/worksheets/sheet1.xml": sheet,
            "xl/sharedStrings.xml": shared,
        },
    )


def preview_files(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*.preview*") if p.is_file()]


def test_image_preview_is_a_private_cached_thumbnail(kit):  # noqa: F811
    client, other, _, directory = kit
    doc = upload(client, image_bytes(), kind="photo").json()
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=86400"
    assert response.headers["x-content-type-options"] == "nosniff"
    thumb = Image.open(io.BytesIO(response.content))
    assert thumb.format == "WEBP"
    assert thumb.size == (640, 360)
    assert len(preview_files(directory)) == 1

    assert other.get(f"/api/app/documents/{doc['id']}/preview").status_code == 404
    client.headers.pop("Authorization")
    assert client.get(f"/api/app/documents/{doc['id']}/preview").status_code == 401


def test_cached_preview_is_served_without_rendering_again(kit, monkeypatch):  # noqa: F811
    client = kit[0]
    doc = upload(client, image_bytes()).json()
    first = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert first.status_code == 200

    async def fail(*_):
        raise AssertionError("rendered twice")

    monkeypatch.setattr(previews, "_render", fail)
    again = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert again.status_code == 200
    assert again.content == first.content


def test_photo_preview_follows_exif_rotation(kit):  # noqa: F811
    client = kit[0]
    exif = Image.Exif()
    exif[0x0112] = 6  # rotated 90 degrees, as phone cameras save portrait shots
    doc = upload(client, image_bytes((1200, 800), "JPEG", exif)).json()
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    width, height = Image.open(io.BytesIO(response.content)).size
    assert height > width


def test_pdf_preview_renders_the_first_page(kit):  # noqa: F811
    client = kit[0]
    doc = upload(client, pdf_bytes()).json()
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/webp"
    width, height = Image.open(io.BytesIO(response.content)).size
    assert width == 640 and 900 < height < 910


def test_unreadable_pdf_has_no_preview_and_the_answer_is_cached(kit, monkeypatch):  # noqa: F811
    client, _, _, directory = kit
    doc = upload(client, PDF).json()
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert response.status_code == 204
    assert [p.suffix for p in preview_files(directory)] == [".none"]

    async def fail(*_):
        raise AssertionError("rendered twice")

    monkeypatch.setattr(previews, "_render", fail)
    assert client.get(f"/api/app/documents/{doc['id']}/preview").status_code == 204


def test_timeout_answers_503_and_is_not_cached(kit, monkeypatch):  # noqa: F811
    client, _, _, directory = kit
    doc = upload(client, image_bytes()).json()

    async def slow(*_):
        raise TimeoutError

    monkeypatch.setattr(previews, "_render", slow)
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert response.status_code == 503
    assert not preview_files(directory)


def test_word_csv_and_excel_previews_are_excerpts(kit):  # noqa: F811
    client = kit[0]
    word = upload(client, docx(["Esmond Adjei", "", "Software engineer, Accra"])).json()
    response = client.get(f"/api/app/documents/{word['id']}/preview")
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "type": "text",
        "paragraphs": ["Esmond Adjei", "Software engineer, Accra"],
    }

    sheet = client.post(
        "/api/app/documents",
        data={"kind": "budget", "title": "Budget"},
        files={"file": ("b.csv", b"item,amount\nSupplies,10\n\nRent,\n", "text/csv")},
    ).json()
    response = client.get(f"/api/app/documents/{sheet['id']}/preview")
    assert response.json() == {
        "type": "table",
        "rows": [["item", "amount"], ["Supplies", "10"], ["Rent", ""]],
    }

    book = upload(client, xlsx(), kind="budget").json()
    assert book["content_type"] == XLSX
    response = client.get(f"/api/app/documents/{book['id']}/preview")
    assert response.json() == {
        "type": "table",
        "rows": [["Item", "", "Cost (GHS)"], ["Laptop", "", "4200"]],
    }


def test_office_embedded_thumbnail_wins_over_text(kit):  # noqa: F811
    client = kit[0]
    deck = office(
        "ppt/presentation.xml",
        "presentationml.presentation.main+xml",
        {
            "ppt/presentation.xml": "<presentation/>",
            "ppt/slides/slide1.xml": f'<p:sld xmlns:p="p" xmlns:a="{A}"><a:p><a:r><a:t>Siwa</a:t></a:r></a:p></p:sld>',
            "docProps/thumbnail.jpeg": image_bytes((256, 192), "JPEG"),
        },
    )
    doc = upload(client, deck, kind="pitch_deck").json()
    assert doc["content_type"] == PPTX
    response = client.get(f"/api/app/documents/{doc['id']}/preview")
    assert response.headers["content-type"] == "image/webp"


def test_slide_text_is_the_fallback_for_decks(tmp_path):
    source = tmp_path / "deck"
    source.write_bytes(
        office(
            "ppt/presentation.xml",
            "presentationml.presentation.main+xml",
            {
                "ppt/slides/slide10.xml": f'<s xmlns:a="{A}"><a:p><a:r><a:t>Later</a:t></a:r></a:p></s>',
                "ppt/slides/slide2.xml": f'<s xmlns:a="{A}"><a:p><a:r><a:t>Siwa water</a:t></a:r></a:p></s>',
            },
        )
    )
    base = tmp_path / "out"
    assert preview_render.render(source, PPTX, base) == "application/json"
    assert (
        tmp_path / "out.json"
    ).read_text() == '{"type": "text", "paragraphs": ["Siwa water"]}'


def test_legacy_office_formats_have_no_preview(tmp_path):
    source = tmp_path / "old.doc"
    source.write_bytes(b"\xd0\xcf\x11\xe0")
    assert preview_render.render(source, "application/msword", tmp_path / "out") is None
    assert not list(tmp_path.glob("out*"))


def test_inflated_xml_is_cut_off_at_the_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(preview_render, "MAX_XML_BYTES", 4096)
    source = tmp_path / "bomb.docx"
    huge = office(
        "word/document.xml",
        "wordprocessingml.document.main+xml",
        {
            "word/document.xml": f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>'
            + "a" * 5_000_000
        },
    )
    source.write_bytes(huge)
    with pytest.raises(Exception, match="no element found|unclosed token"):
        preview_render.render(source, DOCX, tmp_path / "out")


def test_long_text_is_trimmed_and_control_characters_dropped():
    assert preview_render.clean("a\x00b\x07  c\n\td") == "ab c d"
    assert preview_render.clean("x" * 50, 10) == "xxxxxxxxx…"


def test_delete_removes_the_cached_preview(kit):  # noqa: F811
    client, _, ids, directory = kit
    doc = upload(client, image_bytes()).json()
    assert client.get(f"/api/app/documents/{doc['id']}/preview").status_code == 200
    assert preview_files(directory)
    assert client.delete(f"/api/app/documents/{doc['id']}").status_code == 204
    assert not [p for p in directory.rglob("*") if p.is_file()]
    assert not rows(models.Document, ids[0])
