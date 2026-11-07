import io

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from pypdf import PdfReader

from api.cv import docx_export, markdown, pdf_export

FIXTURE = """# Ama Mensah

ama@example.com · [github.com/ama](https://github.com/ama)

## Education

### MSc Robotics, Edinburgh

- **Distinction**; thesis on *tactile* grasping, <u>supervised</u> by Prof. Owusu.
  - Courses: robot learning, `ROS 2`.
1. First numbered
2. Second numbered

---

A paragraph that runs
over two source lines.
"""


def _long_cv(sections: int = 9, items: int = 12) -> str:
    lines = ["# Ama Mensah", "", "ama@example.com", ""]
    for s in range(sections):
        lines += [f"## Section {s}", ""]
        for i in range(items):
            lines.append(f"- Item {s}.{i}: built a pipeline that raised grasp success from 61% to 84% over 1,200 trials.")
        lines.append("")
    return "\n".join(lines)


def test_layout_matches_the_pdf_pages():
    md = _long_cv()
    out = pdf_export.layout(md)
    pdf = PdfReader(io.BytesIO(pdf_export.build_pdf(md)))
    assert out["pages"] == len(pdf.pages) >= 3
    assert [b["page"] for b in out["breaks"]] == list(range(2, len(pdf.pages) + 1))
    source = md.splitlines()
    for b in out["breaks"]:
        first_on_page = pdf.pages[b["page"] - 1].extract_text().splitlines()[0]
        expected = source[b["line"] - 1].lstrip("-# ").strip()
        assert first_on_page.lstrip("\x7f•· ").startswith(expected[:30])


def test_a_short_cv_has_one_page_and_no_breaks():
    assert pdf_export.layout(FIXTURE) == {"pages": 1, "breaks": []}
    assert pdf_export.layout("") == {"pages": 1, "breaks": []}


def test_a_paragraph_split_across_pages_breaks_before_the_next_block():
    long_paragraph = " ".join(["Word"] * 900)
    md = f"# Name\n\n{long_paragraph}\n\n## After\n\nTail."
    out = pdf_export.layout(md)
    assert out["pages"] >= 2
    # The paragraph starts on page 1, so page 2 has no block of its own
    # starting on it unless the heading after it got there.
    for b in out["breaks"]:
        assert b["line"] != 3


def test_pdf_underlines_and_draws_rules():
    assert pdf_export.inline("a <u>b</u> & c") == "a <u>b</u> &amp; c"
    assert "<u>" not in pdf_export.inline("a &lt;u&gt; b")
    pdf = pdf_export.build_pdf(FIXTURE)
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "<u>" not in text and "supervised" in text and "---" not in text


def test_plain_text_drops_underline_tags():
    assert markdown.to_plain_text("A <u>b</u> c") == "A b c\n"


def _docx(md: str = FIXTURE):
    return Document(io.BytesIO(docx_export.build_docx(md, "Ama's CV")))


def test_docx_maps_headings_and_lists_to_word_styles():
    doc = _docx()
    paras = [(p.style.name, p.text) for p in doc.paragraphs if p.text]
    assert paras[0] == ("Title", "Ama Mensah")
    assert ("Heading 1", "Education") in paras
    assert ("Heading 2", "MSc Robotics, Edinburgh") in paras
    assert ("List Bullet", "Distinction; thesis on tactile grasping, supervised by Prof. Owusu.") in paras
    assert ("List Bullet 2", "Courses: robot learning, ROS 2.") in paras
    assert ("List Number", "First numbered") in paras
    assert ("Normal", "A paragraph that runs over two source lines.") in paras
    assert doc.core_properties.title == "Ama's CV"


def test_docx_keeps_inline_marks_as_runs():
    doc = _docx()
    bullet = next(p for p in doc.paragraphs if p.text.startswith("Distinction"))
    runs = {r.text: r for r in bullet.runs}
    assert runs["Distinction"].bold
    assert runs["tactile"].italic
    assert runs["supervised"].underline
    assert not runs["; thesis on "].bold
    code = next(p for p in doc.paragraphs if p.text.startswith("Courses"))
    assert next(r for r in code.runs if r.text == "ROS 2").font.name == "Courier New"


def test_docx_links_are_hyperlinks():
    doc = _docx()
    contact = doc.paragraphs[1]
    links = contact._p.findall(qn("w:hyperlink"))
    assert len(links) == 1
    rel = doc.part.rels[links[0].get(qn("r:id"))]
    assert rel.target_ref == "https://github.com/ama" and rel.is_external
    assert "github.com/ama" in "".join(t.text for t in links[0].iter(qn("w:t")))


def test_docx_page_matches_the_pdf():
    doc = _docx()
    section = doc.sections[0]
    # Word stores twentieths of a point: equal to a hundredth of a mm.
    assert round(section.page_width.mm, 1) == 210 and round(section.page_height.mm, 1) == 297
    assert round(section.left_margin.mm, 1) == pdf_export.MARGIN_X_MM
    assert round(section.top_margin.mm, 1) == pdf_export.MARGIN_Y_MM
    normal = doc.styles["Normal"]
    assert normal.font.size == Pt(pdf_export.BODY_PT) and normal.font.name == docx_export.FONT
    assert doc.styles["Title"].font.size == Pt(pdf_export.NAME_PT)
    assert doc.styles["Heading 1"].font.size == Pt(pdf_export.SECTION_PT)
    rules = [p for p in doc.paragraphs if p._p.pPr is not None and p._p.pPr.find(qn("w:pBdr")) is not None]
    assert len(rules) == 1 and rules[0].text == ""
    assert doc.styles["Heading 1"].element.pPr.find(qn("w:pBdr")) is not None


def test_docx_of_empty_text_is_a_valid_document():
    assert _docx("").paragraphs is not None
