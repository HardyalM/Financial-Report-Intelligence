"""Upload intake: size, signature and password checks, SHA-256, digital-born score."""

from finintel.ingest.digital_born import (
    MIN_EXTRACTABLE_CHARS,
    MIN_PASSING_PAGE_SHARE,
    DigitalBornScore,
    score_digital_born,
)
from finintel.ingest.document import (
    MAX_UPLOAD_BYTES,
    DocumentRecord,
    IngestError,
    IngestErrorCode,
    ingest,
    sha256_file,
)

__all__ = [
    "MAX_UPLOAD_BYTES",
    "MIN_EXTRACTABLE_CHARS",
    "MIN_PASSING_PAGE_SHARE",
    "DigitalBornScore",
    "DocumentRecord",
    "IngestError",
    "IngestErrorCode",
    "ingest",
    "score_digital_born",
    "sha256_file",
]
