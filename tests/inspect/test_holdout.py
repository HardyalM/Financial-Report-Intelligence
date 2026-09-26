"""M1 gate: fixtures/holdout/ is never read by the inspector (EVAL section 1).

`pytest tests/inspect -k holdout` selects every test in this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from finintel.cli import main
from finintel.cli.inspect import (
    HoldoutRefusedError,
    InspectOptions,
    inspect_pdf,
    is_holdout,
    resolve_targets,
)

ROOT = Path(__file__).resolve().parents[2]


def _layout(mini_pdf_master: Path) -> tuple[Path, Path]:
    pdfs, holdout = Path("fixtures/pdfs"), Path("fixtures/holdout")
    pdfs.mkdir(parents=True)
    holdout.mkdir(parents=True)
    (pdfs / "company_a.pdf").write_bytes(mini_pdf_master.read_bytes())
    (holdout / "company_c.pdf").write_bytes(mini_pdf_master.read_bytes())
    return pdfs, holdout


def test_holdout_file_is_refused_before_it_is_read(capsys: pytest.CaptureFixture[str]) -> None:
    Path("fixtures/holdout").mkdir(parents=True)
    bait = Path("fixtures/holdout/company_c.pdf")
    bait.write_bytes(b"not a pdf")  # if it were read, the error would be not_a_pdf
    assert main(["inspect", str(bait), "--out", "out"]) == 3
    err = capsys.readouterr().err
    assert "held out until M8.3" in err and "not_a_pdf" not in err
    assert not Path("out").exists()


def test_holdout_directory_is_refused(
    mini_pdf_master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _layout(mini_pdf_master)
    assert main(["inspect", "fixtures/holdout", "--out", "out"]) == 3
    assert not Path("out").exists()


def test_fixtures_flag_covers_pdfs_only_never_holdout(
    mini_pdf_master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _layout(mini_pdf_master)
    assert main(["inspect", "--fixtures", "--out", "out", "--cache-dir", "cache"]) == 0
    assert [p.name for p in Path("out").iterdir()] == ["company_a"]


def test_fixtures_parent_directory_does_not_recurse_into_holdout(
    mini_pdf_master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _layout(mini_pdf_master)
    assert resolve_targets([Path("fixtures")], fixtures=False) == []


def test_symlink_into_holdout_is_refused(mini_pdf_master: Path) -> None:
    _, holdout = _layout(mini_pdf_master)
    sneaky = Path("fixtures/pdfs/sneaky.pdf")
    sneaky.symlink_to((holdout / "company_c.pdf").resolve())
    with pytest.raises(HoldoutRefusedError):
        resolve_targets([Path("fixtures/pdfs")], fixtures=False)


def test_inspect_pdf_refuses_holdout_directly(mini_pdf_master: Path, tmp_path: Path) -> None:
    _, holdout = _layout(mini_pdf_master)
    options = InspectOptions(out_dir=tmp_path / "out", cache_dir=tmp_path / "cache", azure=None)
    with pytest.raises(HoldoutRefusedError):
        inspect_pdf(holdout / "company_c.pdf", options)


@pytest.mark.parametrize(
    ("path", "held_out"),
    [
        ("fixtures/holdout/x.pdf", True),
        ("Fixtures/HoldOut/x.pdf", True),
        ("fixtures/holdout", True),
        ("fixtures/pdfs/holdout.pdf", False),
        ("elsewhere/holdout/x.pdf", False),
        ("fixtures/pdfs/x.pdf", False),
    ],
)
def test_holdout_path_matching(path: str, held_out: bool) -> None:
    assert is_holdout(Path(path)) is held_out


def test_repository_fixture_glob_excludes_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    for target in resolve_targets([], fixtures=True):
        assert target.parent == Path("fixtures/pdfs") and not is_holdout(target)
