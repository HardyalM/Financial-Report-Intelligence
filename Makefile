# Every target runs inside the uv-managed environment. Override RUN= to use another runner.
RUN ?= uv run

.PHONY: help lint format typecheck test contracts contracts-check scope ci inspect eval-e1 eval-e2 eval-e3 eval eval-live migrate test-db

help:
	@echo "make ci              lint, typecheck, test, contracts-check, scope (the standard gate G1 plus G5)"
	@echo "make contracts       regenerate finintel/contracts from schemas/"
	@echo "make inspect         inspection dumps for every PDF in fixtures/pdfs/ (never fixtures/holdout/)"
	@echo "make eval, eval-live arrive in M2.4 (see docs/MILESTONES.md)"

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

eval:  # E1 then E2 for COMPANY (M8.1 gate: company_a E1 and E2 unchanged)
	$(RUN) finintel eval-e1 $(COMPANY) --engines $(ENGINES)
	$(RUN) finintel eval-e2 $(COMPANY)

# STAGE=commentary: local Ollama by default, else extractive; exits 0 either way.
eval-live:
	@test "$(STAGE)" = commentary || { echo "make eval-live supports STAGE=commentary" >&2; exit 2; }
	$(RUN) finintel commentary $(COMPANY)
