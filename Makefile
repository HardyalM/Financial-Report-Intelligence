# Every target runs inside the uv-managed environment. Override RUN= to use another runner.
RUN ?= uv run

.PHONY: help lint format typecheck test contracts contracts-check scope ci inspect eval-e1 eval-e2 eval-e3 eval eval-live migrate test-db

help:
	@echo "make ci              lint, typecheck, test, contracts-check, scope (the standard gate G1 plus G5)"
	@echo "make contracts       regenerate finintel/contracts from schemas/"
	@echo "make inspect         inspection dumps for every PDF in fixtures/pdfs/ (never fixtures/holdout/)"
	@echo "make dev             fresh clone, no keys: Postgres, migrations, company_a end to end"
	@echo "make eval            E1 and E2 for COMPANY (a run_id under artifacts/eval/)"

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format:
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest

contracts:
	$(RUN) python scripts/gen_contracts.py
	$(RUN) python scripts/export_openapi.py

contracts-check:
	$(RUN) python scripts/gen_contracts.py --check
	$(RUN) python scripts/export_openapi.py --check

scope:
	$(RUN) python scripts/gen_scope.py --check
	$(RUN) python scripts/check_scope.py --web-guard

ci: lint typecheck test contracts-check scope

# ---- dev (M8.3): a fresh clone, no API keys. Postgres (reused if already running), migrations,
# then company_a end to end on local engines with extractive commentary; exit 0 = ready.
# company_a's full PDF is git-ignored, so a clone uses the committed golden excerpt
# (statement pages at their original page numbers, ADR-009). DEV_EMBEDDER=bge-m3 needs the
# optional `local` extra (uv sync --extra local); the default needs nothing downloaded.
DEV_PDF ?= $(if $(wildcard fixtures/pdfs/company_a.pdf),fixtures/pdfs/company_a.pdf,tests/golden/company_a/excerpt.pdf)
DEV_EMBEDDER ?= fake
dev:
	@$(RUN) python -c "import psycopg; from finintel.db.migrate import database_url; psycopg.connect(database_url(), connect_timeout=2).close()" 2>/dev/null \
		&& echo "postgres: reachable" \
		|| docker compose up -d --wait db
	$(RUN) python -m finintel.db migrate
	@echo "company_a: $(DEV_PDF)"
	FININTEL_PROVIDER=none $(RUN) finintel run $(DEV_PDF) --engines local --embedder $(DEV_EMBEDDER)

# ---- web (M7): Node 20.9+; the e2e suite serves tests/e2e/fixtures/api, no backend needed
web-install:
	cd web && npm ci && npx playwright install chromium

web-check:
	cd web && npm run typecheck && npm run types:check
	node scripts/check-deps.js

e2e:
	cd web && npx playwright test

ui-fixtures:
	$(RUN) python -m tests.e2e.fixtures.build_fixtures

e2e-live:  # the real API and worker on a throwaway schema; needs `docker compose up -d db`
	cd web && E2E_LIVE=1 npx playwright test; status=$$?; cd .. && \
	$(RUN) python -m tests.e2e.live_server --drop-only; exit $$status

ci-web: web-check e2e

COMPANY ?= company_a
ENGINES ?= local

eval-e1:
	$(RUN) finintel eval-e1 $(COMPANY) --engines $(ENGINES)

eval-e3:
	$(RUN) finintel eval-e3 $(COMPANY) $(if $(LABELS),--labels $(LABELS),)

eval-e2:
	$(RUN) finintel eval-e2 $(COMPANY)

test-db:
	$(RUN) pytest -m network tests/retrieval/test_postgres.py tests/worker tests/api -q

migrate:
	$(RUN) python -m finintel.db migrate

inspect:
	$(RUN) finintel inspect --fixtures

eval:  # E1, then E2 when hand-computed ratios exist (EVAL section 4: n/a for the held-out report)
	$(RUN) finintel eval-e1 $(COMPANY) --engines $(ENGINES)
	@if [ -f fixtures/expected/$(COMPANY).ratios.json ]; then \
		$(RUN) finintel eval-e2 $(COMPANY); \
	else echo "E2 skipped: fixtures/expected/$(COMPANY).ratios.json does not exist"; fi

# STAGE=commentary: local Ollama by default, else extractive; exits 0 either way.
eval-live:
	@test "$(STAGE)" = commentary || { echo "make eval-live supports STAGE=commentary" >&2; exit 2; }
	$(RUN) finintel commentary $(COMPANY)
