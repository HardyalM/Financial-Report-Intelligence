"""Settings: `.env` parsing, precedence, and the shipped `.env.example`."""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.cli import main
from finintel.cli.settings import load_settings, read_dotenv

ROOT = Path(__file__).resolve().parents[2]


def test_read_dotenv(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "export AZURE_DI_ENDPOINT=https://x.example\n"
        "AZURE_DI_KEY='quoted # not a comment'\n"
        'FININTEL_LOG_FORMAT="json"\n'
        "FININTEL_LOG_LEVEL=info  # trailing comment\n"
        "NOT A PAIR\n"
    )
    assert read_dotenv(env) == {
        "AZURE_DI_ENDPOINT": "https://x.example",
        "AZURE_DI_KEY": "quoted # not a comment",
        "FININTEL_LOG_FORMAT": "json",
        "FININTEL_LOG_LEVEL": "info",
    }
    assert read_dotenv(tmp_path / "absent") == {}


def test_environment_wins_over_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("FININTEL_ARTIFACTS_DIR=from-dotenv\nFININTEL_LOG_LEVEL=debug\n")
    settings = load_settings({"FININTEL_ARTIFACTS_DIR": "from-env"}, dotenv)
    assert settings.artifacts_dir == Path("from-env")
    assert settings.cache_dir == Path("from-env/cache")
    assert settings.log_level == "DEBUG"


def test_defaults_without_any_configuration() -> None:
    settings = load_settings({}, None)
    assert settings.artifacts_dir == Path("artifacts") and settings.cache_dir == Path(
        "artifacts/cache"
    )
    assert settings.azure is None and settings.log_format == "console"


def test_shipped_env_example_parses_and_enables_no_vendor() -> None:
    settings = load_settings({}, ROOT / ".env.example")
    assert settings.azure is None  # keys are blank in the example
    assert settings.log_format == "console"


def test_bad_log_format_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("FININTEL_LOG_FORMAT", "xml")
    assert main(["inspect", "x.pdf"]) == 2
    assert "FININTEL_LOG_FORMAT" in capsys.readouterr().err
