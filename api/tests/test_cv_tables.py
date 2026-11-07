import io

from docx import Document
from pypdf import PdfReader

from api.cv import docx_export, markdown, pdf_export, tables

DOC = """# Ama Mensah

## Education

| Degree | Where | Year |
| :----- | :---: | ---: |
| **BSc** Electrical | KNUST | 2024 |
| A \\| B | Accra |

After the table.

1. First
2. Second
"""


def test_rows_split_on_unescaped_pipes_with_optional_outer_pipes():
    assert tables.split_row("| a | b \\| c |") == ["a", "b \\| c"]
    assert tables.split_row("a | b") == ["a", "b"]
    assert tables.is_delimiter_row("| :-- | :-: | --: |")
    assert not tables.is_delimiter_row("| a | b |")


def test_a_table_reads_its_alignment_and_pads_short_rows():
    lines = DOC.splitlines()
    start = lines.index("| Degree | Where | Year |")
    assert tables.starts_table(lines, start)
    table, after = tables.read_table(lines, start)
    assert table.header == ["Degree", "Where", "Year"]
    assert table.align == ["left", "center", "right"]
    assert table.rows[1] == ["A \\| B", "Accra", ""]
    assert lines[after] == ""


def test_written_tables_line_up_and_escape_pipes():
    assert tables.write_table([["a", "bb"], ["c|d", ""]]) == "| a    | bb  |\n| ---- | --- |\n| c\\|d |     |"


def test_the_pdf_draws_the_table_and_numbers_numbered_lists():
    text = PdfReader(io.BytesIO(pdf_export.build_pdf(DOC))).pages[0].extract_text()
    assert "Degree" in text and "KNUST" in text and "A | B" in text
    assert "|" not in text.replace("A | B", "")
    assert "1." in text and "2." in text
    assert pdf_export.layout(DOC)["pages"] == 1


def test_a_long_table_breaks_pages_without_breaking_inside_it_in_the_editor():
    rows = "\n".join(f"| Row {n} | {'word ' * 12} |" for n in range(120))
    doc = f"# Long\n\n| Name | Text |\n| --- | --- |\n{rows}\n\nAfter.\n"
    out = pdf_export.layout(doc)
    assert out["pages"] > 1
    assert all(b["line"] < 3 or b["line"] > 124 for b in out["breaks"])


def test_word_gets_a_real_table_with_a_bold_repeating_header():
    doc = Document(io.BytesIO(docx_export.build_docx(DOC)))
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["Degree", "Where", "Year"]
    assert [c.text for c in table.rows[2].cells] == ["A | B", "Accra", ""]
    assert all(r.bold for r in table.rows[0].cells[0].paragraphs[0].runs)
    assert table.rows[1].cells[0].paragraphs[0].runs[0].bold  # **BSc**
    assert table.rows[0]._tr.trPr.xml.count("tblHeader") == 1
    assert "After the table." in [p.text for p in doc.paragraphs]


def test_plain_text_keeps_cells_apart_by_tabs():
    text = markdown.to_plain_text("| a | b |\n| --- | --- |\n| **c** | d |\n")
    assert text == "a\tb\nc\td\n"


def _cell(row, col, text, table="tbl[1]", p=1):
    return {
        "type": "table_cell",
        "text": text,
        "source": {"part": "word/document.xml", "path": f"{table}/tr[{row}]/tc[{col}]/p[{p}]"},
    }


def test_a_data_table_in_word_comes_in_as_a_table():
    units = [
        {"type": "heading", "text": "Education", "heading_level": 2, "source": {"part": "word/document.xml", "path": "p[1]"}},
        _cell(0, 0, "Degree"), _cell(0, 1, "Year"),
        _cell(1, 0, "BSc | EE"), _cell(1, 1, "2024"),
        {"type": "paragraph", "text": "Below.", "source": {"part": "word/document.xml", "path": "p[2]"}},
    ]
    md = markdown.units_to_markdown(units)
    assert "| Degree    | Year |\n| --------- | ---- |\n| BSc \\| EE | 2024 |" in md
    assert md.index("## Education") < md.index("| Degree") < md.index("Below.")


def test_a_layout_table_in_word_stays_paragraphs():
    # A two-column header: one row, the contact details stacked in a cell.
    units = [
        _cell(0, 0, "Ama Mensah"),
        _cell(0, 1, "ama@example.com"), _cell(0, 1, "Accra", p=2), _cell(0, 1, "+233", p=3),
    ]
    md = markdown.units_to_markdown(units)
    assert "|" not in md and "Ama Mensah" in md and "Accra" in md
