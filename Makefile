# Every target runs inside the uv-managed environment. Override RUN= to use another runner.
RUN ?= uv run

.PHONY: help lint format typecheck test contracts contracts-check scope ci inspect eval eval-live

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

inspect:
	$(RUN) finintel inspect --fixtures

eval eval-live:
	@echo "make $@ is implemented in M2.4 (docs/MILESTONES.md)." >&2; exit 2
