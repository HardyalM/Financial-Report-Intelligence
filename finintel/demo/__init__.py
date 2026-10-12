"""Sample reports for the dashboard: real pipeline output, clearly marked, removable as a set.

Seeding submits bundled PDFs through the normal intake (`submit_pdf`) and the worker runs every
stage on them, so what the dashboard shows is what the product produces: figures read and checked,
ratios computed, a report blocked on its unit, another waiting for its document type, a bank. No
number is written by this module.

Samples are marked `documents.is_sample`. A PDF that is already in the database (a person uploaded
the same file) is left as it is and never marked, so removing the samples never removes a
person's report. Sample commentary is extractive (no model is called for demo data).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from finintel.ingest import ingest
from finintel.worker.context import RunContext
from finintel.worker.runner import submit_pdf

ROOT = Path(__file__).resolve().parents[2]
_E2E = ROOT / "tests" / "e2e" / "fixtures" / "pdfs"


@dataclass(frozen=True)
class Sample:
    path: Path
    shows: str  # what the sample exercises, for the record


SAMPLES: tuple[Sample, ...] = (
    Sample(
        ROOT / "tests" / "golden" / "company_a" / "excerpt.pdf",
        "a real FTSE annual report's statement pages: figures, ratios, cited passages",
    ),
    Sample(_E2E / "example_states.pdf", "every figure state: verified, derived, review, empty"),
    Sample(_E2E / "liquidity_ordered_bank.pdf", "a bank: its own two ratios"),
    Sample(_E2E / "missing_unit.pdf", "blocked until a person confirms the unit"),
    Sample(_E2E / "liquidity_ordered_insurer.pdf", "waiting for its document type"),
)


def seed(conn: psycopg.Connection, ctx: RunContext) -> dict[str, list[int]]:
    """Submit every sample; mark the ones this call created. Returns the ids added and skipped."""
    added: list[int] = []
    skipped: list[int] = []
    for sample in SAMPLES:
        if not sample.path.is_file():
            continue
        sha = ingest(sample.path).sha256
        existing = conn.execute("SELECT id FROM documents WHERE sha256 = %s", (sha,)).fetchone()
        if existing is not None:
            skipped.append(int(existing[0]))  # already here (a sample, or a person's own upload)
            continue
        doc_id = submit_pdf(conn, ctx, sample.path)
        conn.execute("UPDATE documents SET is_sample = true WHERE id = %s", (doc_id,))
        added.append(doc_id)
    return {"added": added, "skipped": skipped}


def clear(conn: psycopg.Connection) -> list[int]:
    """Remove every sample report (and, by cascade, its jobs, packs and commentary)."""
    rows = conn.execute("DELETE FROM documents WHERE is_sample RETURNING id").fetchall()
    return sorted(int(r[0]) for r in rows)


def is_sample(conn: psycopg.Connection, document_id: int) -> bool:
    row = conn.execute("SELECT is_sample FROM documents WHERE id = %s", (document_id,)).fetchone()
    return bool(row and row[0])
