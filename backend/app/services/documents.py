"""Turn uploaded files (txt, md, pdf, docx) into clean plain text.

This is the only place that knows about file formats. Everything downstream
works on the normalized text returned by `extract_text`, and all character
offsets (segments, quote highlights) refer to that exact string.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import PurePath

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB: far above any real transcript

TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


class DocumentError(ValueError):
    """Base class for problems with an uploaded document. Messages are user-facing."""


class UnsupportedFileTypeError(DocumentError):
    pass


class FileTooLargeError(DocumentError):
    pass


class EmptyDocumentError(DocumentError):
    pass


# Characters that look like whitespace but break exact matching later on.
_SPACE_LIKE = dict.fromkeys(map(ord, "     　"), " ")
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Normalize line endings, odd spaces and invisible characters.

    Letters, punctuation and quote styles are kept as-is so quotes stay
    verbatim; only layout noise is removed.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_SPACE_LIKE).translate(_INVISIBLE)
    text = _TRAILING_WS.sub("", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip("\n")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        raise DocumentError("Could not read this PDF (it may be corrupted or encrypted).") from exc
    return "\n\n".join(pages)


def _docx_text(data: bytes) -> str:
    import zipfile

    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise DocumentError("Could not read this .docx file.") from exc
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> str:
    """Extract normalized plain text from an uploaded file.

    Raises a `DocumentError` subclass with a user-facing message when the file
    is too large, of an unsupported type, unreadable, or empty.
    """
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLargeError(f"{filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"{filename}: unsupported file type. Use {allowed}.")

    if ext == ".pdf":
        raw = _pdf_text(data)
    elif ext == ".docx":
        raw = _docx_text(data)
    else:
        raw = _decode(data)

    text = normalize_text(raw)
    if not text.strip():
        hint = " (scanned PDFs without a text layer are not supported)" if ext == ".pdf" else ""
        raise EmptyDocumentError(f"{filename} contains no text{hint}.")
    return text
