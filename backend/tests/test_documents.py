import io

import pytest
from docx import Document

from app.services.documents import (
    MAX_FILE_BYTES,
    DocumentError,
    EmptyDocumentError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    extract_text,
    normalize_text,
)


def minimal_pdf(text: str) -> bytes:
    """Build a one-page PDF with a text layer (no extra dependency needed)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def test_normalize_text_removes_layout_noise_but_keeps_wording():
    raw = "﻿Interviewer: Hi\r\nMaya: It’s  late​.   \r\n\r\n\r\n\r\nEnd"
    assert normalize_text(raw) == "Interviewer: Hi\nMaya: It’s  late.\n\nEnd"


def test_plain_text_and_cp1252_fallback():
    assert extract_text("a.txt", "Maya: café".encode()) == "Maya: café"
    assert extract_text("a.md", "Maya: café".encode("cp1252")) == "Maya: café"


def test_docx_paragraphs_and_tables():
    doc = Document()
    doc.add_paragraph("Interviewer: How do you get paid?")
    doc.add_paragraph("Maya: Bank transfer, usually late.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Client"
    table.rows[0].cells[1].text = "Days late"
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_text("interview.docx", buf.getvalue())
    assert "Maya: Bank transfer, usually late." in text
    assert "Client | Days late" in text


def test_pdf_text_layer():
    text = extract_text("interview.pdf", minimal_pdf("Maya: I hate chasing invoices."))
    assert "I hate chasing invoices." in text


def test_rejections_have_user_facing_messages():
    with pytest.raises(UnsupportedFileTypeError, match="unsupported file type"):
        extract_text("audio.mp3", b"xx")
    with pytest.raises(FileTooLargeError):
        extract_text("big.txt", b"a" * (MAX_FILE_BYTES + 1))
    with pytest.raises(EmptyDocumentError):
        extract_text("blank.txt", b"  \n\n \t ")
    with pytest.raises(DocumentError):
        extract_text("broken.docx", b"not a zip")
    with pytest.raises(DocumentError):
        extract_text("broken.pdf", b"not a pdf")
