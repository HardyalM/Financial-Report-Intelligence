"""Intake checks: every refusal has a specific code; nothing is repaired or guessed."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from finintel.ingest import (
    DigitalBornScore,
    IngestError,
    IngestErrorCode,
    ingest,
    score_digital_born,
)
from finintel.parse.text_layer import PageText, TextLayer, read_text_layer
from tests.inspect.synthetic import encrypted_pdf, mini_report


def _refused(path: Path, **kwargs: int) -> IngestErrorCode:
    with pytest.raises(IngestError) as caught:
        ingest(path, **kwargs)
    assert caught.value.failure_class == "parse"
    return caught.value.code


def test_record_describes_the_file(mini_pdf: Path) -> None:
    record = ingest(mini_pdf)
    assert record.sha256 == hashlib.sha256(mini_pdf.read_bytes()).hexdigest()
    assert record.filename == "company_x.pdf"
    assert record.size_bytes == mini_pdf.stat().st_size
    assert record.page_count == 7
    assert record.title == "Example Group plc Annual Report 2025"
    assert record.producer == "finintel tests"
    assert record.encryption is None
    assert record.pdf_format is not None and record.pdf_format.startswith("PDF ")


def test_empty_file_is_not_a_pdf(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert _refused(empty) is IngestErrorCode.NOT_A_PDF


def test_other_formats_are_not_pdfs(tmp_path: Path) -> None:
    html = tmp_path / "report.pdf"
    html.write_text("<html><body>Annual report</body></html>")
    assert _refused(html) is IngestErrorCode.NOT_A_PDF


def test_signature_must_be_in_the_first_kib(tmp_path: Path, mini_pdf: Path) -> None:
    late = tmp_path / "late.pdf"
    late.write_bytes(b"\0" * 2048 + mini_pdf.read_bytes())
    assert _refused(late) is IngestErrorCode.NOT_A_PDF


def test_oversized_file_is_refused_with_sizes(mini_pdf: Path) -> None:
    with pytest.raises(IngestError) as caught:
        ingest(mini_pdf, max_bytes=1000)
    assert caught.value.code is IngestErrorCode.FILE_TOO_LARGE
    assert "MB" in caught.value.message


def test_damaged_pdf_is_unreadable(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nthis is not a pdf body\n")
    assert _refused(broken) is IngestErrorCode.UNREADABLE_PDF


def test_password_protected_pdf_is_refused(tmp_path: Path) -> None:
    pdf = encrypted_pdf(tmp_path / "locked.pdf", user_password="open-sesame")
    assert _refused(pdf) is IngestErrorCode.ENCRYPTED_PDF


def test_owner_password_only_is_accepted_and_recorded(tmp_path: Path) -> None:
    """Many annual reports restrict editing but open freely; those are fine to read."""
    pdf = encrypted_pdf(tmp_path / "restricted.pdf", user_password=None)
    record = ingest(pdf)
    assert record.encryption is not None and "AES" in record.encryption


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest(tmp_path / "absent.pdf")


# ---------------------------------------------------------------- digital-born score


def _layer(chars: list[tuple[int, int]]) -> TextLayer:
    pages = tuple(
        PageText(
            page=n, label=None, width=595, height=842, rotation=0, char_count=c,
            replacement_char_count=r,
        )
        for n, (c, r) in enumerate(chars, start=1)
    )  # fmt: skip
    return TextLayer(
        extractor="test", page_count=len(pages), has_page_labels=False, outline=(), pages=pages
    )


def test_text_report_is_digitally_born(mini_pdf: Path) -> None:
    score = score_digital_born(read_text_layer(mini_pdf))
    assert score.is_digitally_born
    assert score.failing_pages == ()
    assert score.passing_page_share == 1.0 and score.glyph_share == 1.0


def test_blank_pages_fail_the_threshold(tmp_path: Path) -> None:
    pdf = mini_report(tmp_path / "with_blanks.pdf", blank_pages=1)
    score = score_digital_born(read_text_layer(pdf))
    assert score.pages_total == 8 and score.pages_passing == 7
    assert score.failing_pages == (8,)
    assert not score.is_digitally_born  # 0.875 < 0.9


def test_page_passes_at_exactly_200_extractable_characters() -> None:
    score = score_digital_born(_layer([(200, 0), (199, 0)]))
    assert score.failing_pages == (2,)


def test_replacement_glyphs_are_not_extractable() -> None:
    score: DigitalBornScore = score_digital_born(_layer([(250, 51), (250, 50)]))
    assert score.failing_pages == (1,)  # 199 real characters
    assert score.glyph_share == round(399 / 500, 4)


def test_ninety_percent_of_pages_is_enough() -> None:
    assert score_digital_born(_layer([(500, 0)] * 9 + [(0, 0)])).is_digitally_born
    assert not score_digital_born(_layer([(500, 0)] * 8 + [(0, 0)] * 2)).is_digitally_born
