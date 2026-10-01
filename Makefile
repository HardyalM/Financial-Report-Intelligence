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

contracts-check:
	$(RUN) python scripts/gen_contracts.py --check

scope:
	$(RUN) python scripts/gen_scope.py --check
	$(RUN) python scripts/check_scope.py --web-guard

ci: lint typecheck test contracts-check scope

COMPANY ?= company_a
ENGINES ?= local

eval-e1:
	$(RUN) finintel eval-e1 $(COMPANY) --engines $(ENGINES)

eval-e3:
	$(RUN) finintel eval-e3 $(COMPANY) $(if $(LABELS),--labels $(LABELS),)

eval-e2:
	$(RUN) finintel eval-e2 $(COMPANY)

test-db:
	$(RUN) pytest -m network tests/retrieval/test_postgres.py -q

migrate:
	$(RUN) python -m finintel.db migrate

inspect:
	$(RUN) finintel inspect --fixtures

eval:
	@echo "make eval is implemented in M2.4 (docs/MILESTONES.md)." >&2; exit 2

# STAGE=commentary: live model if ANTHROPIC_API_KEY is set, else extractive; exits 0 either way.
eval-live:
	@test "$(STAGE)" = commentary || { echo "make eval-live supports STAGE=commentary" >&2; exit 2; }
	$(RUN) finintel commentary $(COMPANY)
