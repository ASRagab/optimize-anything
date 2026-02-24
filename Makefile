.PHONY: test test-fast gates gates-offline smoke score-check score-update install help

test:                     ## Run full test suite
	uv run pytest -v

test-fast:                ## Run tests excluding integration
	uv run pytest -v -m "not integration"

gates:                    ## Run all quality gates
	uv run python scripts/check.py

gates-offline:            ## Run gates without smoke (no API calls)
	uv run python scripts/check.py --skip-smoke

smoke:                    ## Run smoke harness
	uv run python scripts/smoke_harness.py --budget 1

score-check:              ## Check score baselines
	uv run python scripts/score_check.py

score-update:             ## Update score baselines
	uv run python scripts/score_check.py --update

install:                  ## Install dependencies
	uv sync

help:                     ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'
