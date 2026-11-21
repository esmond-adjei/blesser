import json
import logging

import pytest

from api.agent.llm.base import LLMResponse, ToolCall
from api.applicant_kit import cv_import, cv_text
from api.core.config import settings
from tests.test_applicant_kit import kit, upload  # noqa: F401
from tests.test_document_previews import DOCX, W, docx, image_bytes, office, pdf_bytes

pytestmark = pytest.mark.real_auth

CV_LINES = [
    "Ama Serwaa Mensah",
    "Software engineer building tools for smallholder farmers",
    "ama.mensah@example.com | +233 24 123 4567 | Kumasi, Ghana",
    "Ghana Card GHA-123456789-0",
    "Profile",
    "Engineer with five years of experience in agricultural technology.",
    "Experience",
    "Lead Engineer, Siwa Ltd, Kumasi, March 2022 to present",
    "Education",
    "BSc Computer Science, KNUST, 2016 to 2020, First class",
]


def pdf_with_text(lines: list[str]) -> bytes:
    """A small one-page PDF whose text a PDF reader can extract."""
    body = "BT /F1 11 Tf 40 800 Td 14 TL " + " ".join(
        "(" + line.replace("(", r"\(").replace(")", r"\)") + ") '" for line in lines
    )
    stream = body + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


def docx_with_link(lines: list[str], url: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in lines)
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId9" Type="{cv_text.HYPERLINK}" Target="{url}" TargetMode="External"/>'
        "</Relationships>"
    )
    return office(
        "word/document.xml",
        "wordprocessingml.document.main+xml",
        {
            "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>',
            "word/_rels/document.xml.rels": rels,
        },
    )


def empty_fields(**values) -> dict:
    fields = {
        name: [] if field.annotation is not str else ""
        for name, field in cv_import.CvFields.model_fields.items()
    }
    return {**fields, **values}


MODEL_FIELDS = empty_fields(
    given_name="Ama Serwaa",
    family_name="Mensah",
    date_of_birth="March 1998",
    nationality="Ghanaian",
    country_of_residence="Ghana",
    city="Kumasi",
    email="ama.mensah@example.com",
    phone="+233 24 123 4567",
    linkedin_url="linkedin.com/in/ama-mensah",
    github_url="not a url",
    headline="Software engineer building tools for smallholder farmers",
    short_bio=(
        "Ama is an engineer with five years of experience in agricultural technology. "
        + "She builds tools that help farmers sell more of what they grow. " * 6
    ),
    long_bio="Engineer with five years of experience in agricultural technology.",
    education=[
        {
            "institution": "KNUST",
            "qualification": "BSc",
            "field": "Computer Science",
            "grade": "First class",
            "start": "2016",
            "end": "2020-07",
            "country": "Ghana",
        },
        {
            "institution": "",
            "qualification": "",
            "field": "",
            "grade": "",
            "start": "",
            "end": "",
            "country": "",
        },
    ],
    experience=[
        {
            "organization": "Siwa Ltd",
            "role": "Lead Engineer",
            "current": True,
            "start": "2022-03",
            "end": "2024-01",
            "location": "Kumasi",
            "summary": "Built the stock app.",
        },
        {
            "organization": "Farmhub",
            "role": "Engineer",
            "current": False,
            "start": "2021-05",
            "end": "2020-01",
            "location": "",
            "summary": "",
        },
    ],
    skills=["Python", "python", "  Product   design ", ""],
    languages=[
        {"language": "Twi", "level": "native"},
        {"language": "English", "level": ""},
    ],
    awards=[{"title": "Young Innovator", "issuer": "MEST", "year": "20xx"}],
    references=[
        {
            "name": "Dr Kofi Boateng",
            "title": "Senior Lecturer",
            "organization": "KNUST",
            "email": "not an email",
            "phone": "",
            "relationship": "Supervisor",
        }
    ],
)


class FakeProvider:
    def __init__(self, arguments=None, *, error=None, text=""):
        self.calls = []
        self.arguments = arguments
        self.error = error
        self.text = text

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if self.arguments is None:
            return LLMResponse(text=self.text)
        return LLMResponse(
            tool_calls=[ToolCall(id="1", name="cv_profile", arguments=self.arguments)]
        )


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(settings, "llm_turn_retries", 0)

    def use(provider):
        monkeypatch.setattr(cv_import, "get_provider", lambda: provider)
        return provider

    return use


def upload_cv(client, content, filename="cv.pdf", content_type="application/pdf"):
    response = client.post(
        "/api/app/documents",
        data={"kind": "cv", "title": "My CV"},
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def read_cv(client, document_id):
    return client.post("/api/app/profile/from-cv", json={"document_id": document_id})


def test_pdf_cv_fills_valid_fields_and_saves_nothing(kit, model):  # noqa: F811
    client = kit[0]
    before = client.get("/api/app/profile").json()
    provider = model(FakeProvider(MODEL_FIELDS))
    document_id = upload_cv(client, pdf_with_text(CV_LINES))

    response = read_cv(client, document_id)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    profile = response.json()["profile"]
    assert profile["given_name"] == "Ama Serwaa"
    assert profile["family_name"] == "Mensah"
    assert profile["linkedin_url"] == "https://linkedin.com/in/ama-mensah"
    # Values the profile can't hold are left for the member, not guessed.
    for missing in ("date_of_birth", "github_url", "gender", "website_url"):
        assert missing not in profile
    assert len(profile["short_bio"]) <= 300
    assert profile["short_bio"].endswith(".")
    assert profile["education"] == [
        {
            "start": "2016-01-01",
            "end": "2020-07-01",
            "institution": "KNUST",
            "qualification": "BSc",
            "field": "Computer Science",
            "grade": "First class",
            "country": "Ghana",
        }
    ]
    current, swapped = profile["experience"]
    assert current["current"] is True and current["end"] is None
    assert current["start"] == "2022-03-01"
    assert swapped["organization"] == "Farmhub"
    assert swapped["start"] is None and swapped["end"] is None
    assert profile["skills"] == ["Python", "Product design"]
    assert profile["languages"] == [
        {"language": "Twi", "level": "native"},
        {"language": "English", "level": "fluent"},
    ]
    assert profile["awards"] == [
        {"title": "Young Innovator", "issuer": "MEST", "year": None}
    ]
    assert profile["references"][0]["email"] == ""
    assert "sensitive" not in profile

    # The CV went to the model as delimited data, with the PDF's own text.
    call = provider.calls[0]
    assert "<untrusted_content" in call["messages"][0]["content"]
    sent = call["messages"][0]["content"]
    assert "Lead Engineer, Siwa Ltd" in sent
    assert "national ID" in call["system"]
    schema = call["tools"][0]["parameters"]
    assert "sensitive" not in schema["properties"]
    assert "national_id" not in json.dumps(schema)

    assert client.get("/api/app/profile").json() == before


def test_word_cv_text_and_links_are_read(kit, model):  # noqa: F811
    client = kit[0]
    provider = model(FakeProvider(empty_fields(given_name="Ama")))
    content = docx_with_link(CV_LINES, "https://github.com/ama")
    document_id = upload_cv(client, content, "cv.docx", DOCX)

    response = read_cv(client, document_id)

    assert response.status_code == 200, response.text
    assert response.json()["profile"] == {"given_name": "Ama"}
    sent = provider.calls[0]["messages"][0]["content"]
    assert "Software engineer building tools" in sent
    assert "https://github.com/ama" in sent


def test_scanned_pdf_asks_for_a_readable_file(kit, model):  # noqa: F811
    client = kit[0]
    provider = model(FakeProvider(MODEL_FIELDS))
    document_id = upload_cv(client, pdf_bytes())

    response = read_cv(client, document_id)

    assert response.status_code == 422
    assert "scan or a photo" in response.text
    assert provider.calls == []


def test_images_and_short_word_files_are_not_sent(kit, model):  # noqa: F811
    client = kit[0]
    provider = model(FakeProvider(MODEL_FIELDS))
    photo = upload_cv(client, image_bytes(), "cv.png", "image/png")
    assert read_cv(client, photo).status_code == 422
    short = upload_cv(client, docx(["Ama Mensah"]), "cv.docx", DOCX)
    assert read_cv(client, short).status_code == 422
    assert provider.calls == []


def test_another_members_cv_is_not_found(kit, model):  # noqa: F811
    client, other = kit[0], kit[1]
    model(FakeProvider(MODEL_FIELDS))
    document_id = upload_cv(client, pdf_with_text(CV_LINES))

    assert read_cv(other, document_id).status_code == 404
    assert read_cv(client, "missing").status_code == 404


@pytest.mark.parametrize(
    "provider",
    [
        FakeProvider(error=TimeoutError("no reply")),
        FakeProvider(text="not json"),
        FakeProvider({"given_name": "Ama"}),
    ],
)
def test_model_failure_is_retryable_and_never_logs_the_cv(kit, model, provider, caplog):  # noqa: F811
    client = kit[0]
    model(provider)
    document_id = upload_cv(client, pdf_with_text(CV_LINES))

    with caplog.at_level(logging.DEBUG):
        response = read_cv(client, document_id)

    assert response.status_code == 503
    assert "Try again" in response.text
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for line in CV_LINES:
        assert line not in logged


def test_reading_cvs_is_rate_limited():
    from api.core.ratelimit import LIMITS

    assert LIMITS["kit_cv"]


def test_child_reads_docx_tables_and_tabs(tmp_path):
    body = (
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Languages</w:t><w:tab/>"
        "<w:t>Twi, English</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    path = tmp_path / "cv.docx"
    path.write_bytes(
        office(
            "word/document.xml",
            "wordprocessingml.document.main+xml",
            {
                "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>'
                + "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in CV_LINES)
                + body
                + "</w:body></w:document>"
            },
        )
    )
    result = cv_text.read(path, DOCX)
    assert "Languages Twi, English" in result["text"]
    assert cv_text.read(path, "image/png") == {"error": cv_text.UNSUPPORTED}
