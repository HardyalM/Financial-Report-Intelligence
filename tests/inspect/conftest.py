"""Fixtures for the M1 inspection tests.

Every test runs in its own working directory with vendor credentials cleared, so a developer's
`.env` or shell cannot change what the tests exercise.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from finintel.cli.inspect import InspectOptions
from tests.inspect.synthetic import mini_report

ROOT = Path(__file__).resolve().parents[2]
_ENV = (
    "AZURE_DI_ENDPOINT",
    "AZURE_DI_KEY",
    "FININTEL_AZURE_DI_API_VERSION",
    "FININTEL_AZURE_DI_MODEL",
    "FININTEL_ARTIFACTS_DIR",
    "FININTEL_CACHE_DIR",
    "FININTEL_LOG_FORMAT",
    "FININTEL_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    structlog.reset_defaults()  # `main()` configures logging globally; do not leak it
    yield
    structlog.reset_defaults()


@pytest.fixture(scope="session")
def mini_pdf_master(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_report(tmp_path_factory.mktemp("pdfs") / "mini.pdf")


@pytest.fixture
def mini_pdf(tmp_path: Path, mini_pdf_master: Path) -> Path:
    """A private copy of the seven-page synthetic report."""
    target = tmp_path / "company_x.pdf"
    target.write_bytes(mini_pdf_master.read_bytes())
    return target


@pytest.fixture
def options(tmp_path: Path) -> InspectOptions:
    return InspectOptions(out_dir=tmp_path / "out", cache_dir=tmp_path / "cache", azure=None)
