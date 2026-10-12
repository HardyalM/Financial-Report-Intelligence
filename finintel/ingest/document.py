"""Upload checks: size, PDF signature, password protection, readability, SHA-256.

A failed check raises `IngestError` with a specific code; nothing is guessed or repaired.
Storing the original under its SHA-256 arrives with the object store (M6.1). Until then the
content-addressed stage cache (finintel.cache) is keyed by the same hash.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

import pymupdf
from pydantic import BaseModel, ConfigDict

#: Upload limit (PLAN J1). The API returns 413 above it (ARCHITECTURE section 4, stage 1).
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_SIGNATURE = b"%PDF-"
_SIGNATURE_WINDOW = 1024  # the PDF header may sit anywhere in the first 1 KiB


class IngestErrorCode(StrEnum):
    NOT_A_PDF = "not_a_pdf"
    FILE_TOO_LARGE = "file_too_large"
    ENCRYPTED_PDF = "encrypted_pdf"
    UNREADABLE_PDF = "unreadable_pdf"


class IngestError(Exception):
    """An upload the pipeline refuses. `failure_class` follows the product's failure taxonomy."""

    failure_class = "parse"

    def __init__(self, code: IngestErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message


class DocumentRecord(BaseModel):
    """A PDF that passed intake checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str
    filename: str
    size_bytes: int
    page_count: int
    pdf_format: str | None  # e.g. "PDF 1.7"
    producer: str | None
    creator: str | None
    title: str | None
    #: Encryption method when the PDF has only an owner password (it opens without one).
    #: Such files are accepted: many annual reports restrict editing, not reading.
    encryption: str | None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def ingest(pdf_path: Path, *, max_bytes: int = MAX_UPLOAD_BYTES) -> DocumentRecord:
    """Check a PDF and describe it. Raises `IngestError`; `FileNotFoundError` if absent."""
    size = pdf_path.stat().st_size
    if size == 0:
        raise IngestError(IngestErrorCode.NOT_A_PDF, f"{pdf_path.name} is empty")
    if size > max_bytes:
        raise IngestError(
            IngestErrorCode.FILE_TOO_LARGE,
            f"{pdf_path.name} is {size / 1_048_576:.1f} MB; the limit is "
            f"{max_bytes / 1_048_576:.0f} MB",
        )
    with pdf_path.open("rb") as handle:
        if _SIGNATURE not in handle.read(_SIGNATURE_WINDOW):
            raise IngestError(
                IngestErrorCode.NOT_A_PDF, f"{pdf_path.name} has no %PDF- header in its first 1 KiB"
            )

    try:
        doc = pymupdf.open(pdf_path, filetype="pdf")
    except Exception as exc:  # MuPDF raises FileDataError, RuntimeError, ... for damaged files
        raise IngestError(
            IngestErrorCode.UNREADABLE_PDF,
            # Not MuPDF's own text: it names the server path the upload was written to.
            f"{pdf_path.name} could not be opened: it is damaged or not a complete PDF",
        ) from exc
    with doc:
        if doc.needs_pass:
            raise IngestError(
                IngestErrorCode.ENCRYPTED_PDF,
                f"{pdf_path.name} needs a password to open; upload an unprotected copy",
            )
        if doc.page_count < 1:
            raise IngestError(IngestErrorCode.UNREADABLE_PDF, f"{pdf_path.name} has no pages")
        meta = doc.metadata or {}
        return DocumentRecord(
            sha256=sha256_file(pdf_path),
            filename=pdf_path.name,
            size_bytes=size,
            page_count=doc.page_count,
            pdf_format=meta.get("format") or None,
            producer=meta.get("producer") or None,
            creator=meta.get("creator") or None,
            title=meta.get("title") or None,
            encryption=meta.get("encryption") or None,
        )
