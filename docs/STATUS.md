# STATUS

Session log. Commands and results only. Newest first.

Toolchain on the tech lead's machine: `uv` 0.12.19 (installed with `python3 -m pip install --user uv`,
binary at `~/Library/Python/3.9/bin/uv`), CPython 3.12.14 via `uv python install 3.12`.

---

## M1 — 2026-09-26 — built, gate BLOCKED on fixtures

M1 code complete and green offline. Gate blocked: `fixtures/pdfs/` empty; only `EXAMPLE_company_a.json`.
Not advancing to M2.1.

| Command | Result |
|---|---|
| `make ci` | exit 0: ruff clean, strict mypy clean (64 files), **211 passed, 1 skipped** (`test_fixture_pdfs`: no PDFs), contracts and scope up to date |
| `uv run python scripts/check_scope.py M1 --base m0` | exit 0 |
| `uv run pytest tests/inspect -k holdout` | 13 passed |
| `uv run finintel inspect fixtures/pdfs/company_a.pdf` | exit 1: `no such file`; `vendor_calls=0` |
| `make inspect` (`finintel inspect --fixtures`) | exit 1: `no PDFs found. fixtures/pdfs/ is filled by the tech lead` |
| 280-page synthetic report, cold / warm cache | 1.95 s / 0.22 s (text layer 995 ms, pdfplumber on 40 candidate pages 796 ms). Synthetic pages are lighter than a typeset report; re-measure on `company_a`. |

What `finintel inspect <pdf>` writes to `artifacts/inspect/{stem}/`: `summary.json` (document record,
digital-born score, engines run/skipped/failed, top-10 statement-titled pages, specific warnings, run
trace with per-stage cache status, ms, vendor calls and estimated cost), `pages.jsonl`, `outline.json`,
`text/`, `tables/` (raw pdfplumber, `lines` and `text` strategies), `thumbs/`, `azure/raw.json` when keyed.

Decisions taken inside M1 (no plan change):
- OQ-7 unanswered, so its default applies: Azure DI on the whole document; `--azure-pages` is the B flag.
- Owner-password-only PDFs are accepted (they open without a password; many annual reports restrict
  editing). Only PDFs that need a password to open are refused (`encrypted_pdf`).
- pdfplumber runs on candidate pages by default (top 20 ranked, plus any further statement-titled
  page, max 40); `--tables all` for every page. COST_AND_OPS: never pdfplumber on every page by default.
- An Azure failure of any kind degrades to `parser_failed: ["azure_di"]`, is never cached, and the
  local path completes. Found by a test: a non-httpx network error used to crash the whole run.

Open for the tech lead: the ROCE conflict between the session prompt and `CLAUDE.md` (see the M1 report).

---

## M0 — 2026-09-26 — green

M0 green on Python 3.12. `uv.lock` committed. Sign-off on package layout still open (tech lead).

| Command | Result |
|---|---|
| `uv lock` | resolved 28 packages |
| `make ci` | exit 0: ruff clean, 67 files formatted, strict mypy clean (44 files), 66 passed, contracts up to date, scope.yaml up to date, web guard passed |
| `uv run python scripts/check_scope.py M0 --base main` | exit 0 |
| `uv run python scripts/check_imports.py --forbid fitz,pdfplumber,httpx,anthropic,voyageai` | exit 0 |

Change to the gate machinery: `docs/STATUS.md` added to the G2 global allow-list (MILESTONES G2
row, regenerated `scripts/scope.yaml`), so every session can log here without failing G2.
