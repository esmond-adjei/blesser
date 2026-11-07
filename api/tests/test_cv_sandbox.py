import asyncio
import io
import json
import zipfile

import pytest

from api.core.config import settings
from api.cv import engine, sandbox
from tests.cv_fixtures import corpus_simple


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


CT = b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
DOC = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'

MALICIOUS = {
    "zip_bomb": _zip(
        {
            "[Content_Types].xml": CT,
            "word/document.xml": DOC,
            "word/pad.xml": b"0" * 60_000_000,
        }
    ),
    "xxe": _zip(
        {
            "[Content_Types].xml": CT,
            "word/document.xml": b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            + DOC.replace(b"<w:body/>", b"<w:body>&x;</w:body>"),
        }
    ),
    "macro": _zip(
        {
            "[Content_Types].xml": CT,
            "word/document.xml": DOC,
            "word/vbaProject.bin": b"\x00" * 64,
        }
    ),
    "traversal": _zip(
        {"[Content_Types].xml": CT, "word/document.xml": DOC, "../../etc/evil": b"x"}
    ),
}


@pytest.fixture(autouse=True)
def _process_mode(monkeypatch):
    monkeypatch.setattr(settings, "cv_sandbox", "process")


@pytest.mark.parametrize("name", sorted(MALICIOUS))
def test_malicious_fixtures_fail_closed_in_the_sandbox(name):
    with pytest.raises(engine.CvEngineError) as exc:
        asyncio.run(sandbox.extract_docx(MALICIOUS[name], "cv.docx"))
    assert exc.value.code in {
        "zip_bomb",
        "xxe",
        "macro_enabled",
        "path_traversal",
        "entry_too_large",
    }


def test_valid_document_round_trips_through_the_sandbox():
    ir = asyncio.run(sandbox.extract_docx(corpus_simple(), "cv.docx"))
    assert any("Research assistant" in (u.text or "") for u in ir.units)


def _pdf(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


def test_pdf_text_is_read_in_the_sandbox():
    pages = asyncio.run(sandbox.extract_pdf(_pdf(["Jane Doe", "EDUCATION", "PhD student, 2024"])))
    assert "PhD student, 2024" in pages[0]


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not a pdf at all", "bad_magic"),
        (b"%PDF-1.7\n%garbage that never ends", "bad_pdf"),
    ],
)
def test_bad_pdfs_fail_closed_in_the_sandbox(data, code):
    with pytest.raises(engine.CvEngineError) as exc:
        asyncio.run(sandbox.extract_pdf(data))
    assert exc.value.code == code


def test_a_pdf_with_no_text_is_refused():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(100, 100, 200, 200, fill=1)  # a "scan": shapes, no text layer
    c.save()
    with pytest.raises(engine.CvEngineError) as exc:
        asyncio.run(sandbox.extract_pdf(buf.getvalue()))
    assert exc.value.code == "no_text"


def test_hung_job_is_killed_at_the_wall_clock_without_wedging(tmp_path, monkeypatch):
    import os
    import subprocess
    import time

    marker = f"hung-{os.getpid()}"
    fake = tmp_path / "fake-python"
    # Stand-in interpreter that hangs and leaves a child in the same process group.
    fake.write_text(f"#!/bin/sh\nsleep 30 {marker} &\nsleep 30\n")
    fake.chmod(0o755)
    monkeypatch.setattr(sandbox.sys, "executable", str(fake))
    monkeypatch.setattr(sandbox, "_netns_available", lambda: False)
    monkeypatch.setitem(
        sandbox.LIMITS, "parse", {"mem_mb": 1024, "cpu_s": 30, "wall_s": 1}
    )
    started = time.monotonic()
    with pytest.raises(sandbox.SandboxLimitError) as exc:
        asyncio.run(sandbox.extract_docx(corpus_simple(), "cv.docx"))
    assert exc.value.code == "timeout"
    assert time.monotonic() - started < 5
    time.sleep(0.2)
    leftovers = subprocess.run(
        ["pgrep", "-f", marker], capture_output=True, text=True, check=False
    ).stdout
    assert leftovers.strip() == "", "the whole process group must be killed"


def test_memory_bomb_is_contained(monkeypatch):
    monkeypatch.setitem(
        sandbox.LIMITS, "parse", {"mem_mb": 256, "cpu_s": 10, "wall_s": 20}
    )
    huge = _zip(
        {
            "[Content_Types].xml": CT,
            "word/document.xml": DOC.replace(
                b"<w:body/>", b"<w:body>" + b"<w:p/>" * 3_000_000 + b"</w:body>"
            ),
        }
    )
    with pytest.raises((sandbox.SandboxLimitError, engine.CvEngineError)):
        asyncio.run(sandbox.extract_docx(huge, "cv.docx"))


def test_child_sees_no_secrets_and_no_network(tmp_path, monkeypatch):
    """Run a probe inside the exact child setup the sandbox uses."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/testdb")
    monkeypatch.setenv("AUTH_SECRET", "dummy-value-for-env-scrub-test")
    probe = (
        "import json, os, socket\n"
        "net = 'blocked'\n"
        "try:\n"
        "    s = socket.socket(); s.settimeout(2); s.connect(('1.1.1.1', 80)); net = 'open'\n"
        "except OSError:\n"
        "    pass\n"
        "print(json.dumps({'env': sorted(os.environ), 'net': net}))\n"
    )
    import shutil
    import subprocess
    import sys

    cmd = [sys.executable, "-I", "-c", probe]
    if sandbox._netns_available():
        cmd = [shutil.which("unshare"), "--user", "--net", "--map-root-user", *cmd]
    out = subprocess.run(
        cmd,
        env=sandbox._child_env(str(tmp_path)),
        preexec_fn=sandbox._limits("parse"),
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    report = json.loads(out)
    assert not {"DATABASE_URL", "AUTH_SECRET"} & set(report["env"])
    if sandbox._netns_available():
        assert report["net"] == "blocked"
    assert sandbox.sandbox_status()["mode"] == "process"
