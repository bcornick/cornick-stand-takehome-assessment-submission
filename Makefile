# ABOUTME: Developer entry points: check, test-slow, up and eval.
# ABOUTME: Targets that call compose set GIT_COMMIT for the image build argument.
GIT_COMMIT := $(shell git rev-parse HEAD)
export GIT_COMMIT

FAST := not slow and not integration and not integration_record and not integration_replay

.PHONY: check test-slow up eval

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	python3 scripts/check_discipline.py
	uv run pytest -m "$(FAST)"
	pnpm --dir web exec tsc -b
	pnpm --dir web exec vitest run

test-slow:
	uv run pytest -m "slow or integration"

up:
	docker compose up --build

eval:
	docker compose --profile eval run --build --rm $(RUN_OPTS) eval $(ARGS)
