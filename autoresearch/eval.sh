#!/usr/bin/env bash
# Autoresearch eval harness for optimize-anything
# Outputs a composite score (0-100) based on 4 metrics.
# Tests are a hard gate: any failure = score 0.
# DO NOT MODIFY THIS FILE — it is read-only for the experiment agent.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

BASELINE_LOC=3378

# ── Hard gate: all tests must pass ──
TEST_OUTPUT=$(uv run python -m pytest -m "not integration" --tb=no 2>&1) || true
if echo "$TEST_OUTPUT" | grep -qE "FAILED|ERROR"; then
  echo "tests=FAIL"
  echo "score: 0.00"
  exit 0
fi

TESTS_PASSED=$(echo "$TEST_OUTPUT" | grep -oP '(\d+) passed' | grep -oP '^\d+')

# ── Coverage ──
COV_OUTPUT=$(uv run python -m pytest -m "not integration" --cov=optimize_anything --cov-report=term -q --tb=no 2>&1) || true
COV=$(echo "$COV_OUTPUT" | grep "^TOTAL" | awk '{print $NF}' | tr -d '%')
if [ -z "$COV" ]; then COV=0; fi

# ── Complexity (average CC) ──
CC_OUTPUT=$(uv run radon cc src/optimize_anything/ -a 2>&1) || true
AVG_CC=$(echo "$CC_OUTPUT" | tail -1 | grep -oP '[\d.]+' | tail -1)
if [ -z "$AVG_CC" ]; then AVG_CC=10; fi

# ── Type errors (mypy) ──
MYPY_OUTPUT=$(uv run mypy src/optimize_anything/ --ignore-missing-imports 2>&1) || true
MYPY_ERRORS=$(echo "$MYPY_OUTPUT" | grep -c "error:" || echo "0")

# ── LOC ──
CURRENT_LOC=$(cat src/optimize_anything/*.py | wc -l)

# ── Compute composite score ──
python3 -c "
cov = min(float('${COV}'), 100)
avg_cc = float('${AVG_CC}')
mypy_err = int('${MYPY_ERRORS}')
current_loc = int('${CURRENT_LOC}')
baseline_loc = ${BASELINE_LOC}
loc_ratio = baseline_loc / max(current_loc, 1)

cov_score = cov
cc_score = max(0, 100 - (avg_cc - 1) * 10)
type_score = max(0, 100 - mypy_err * 4)
loc_score = min(130, 100 * loc_ratio)

final = 0.25 * cov_score + 0.25 * cc_score + 0.25 * type_score + 0.25 * loc_score

tests_passed = '${TESTS_PASSED}' or '0'
print(f'tests={tests_passed} coverage={cov:.1f}% complexity_avg={avg_cc:.2f} mypy_errors={mypy_err} loc={current_loc}')
print(f'sub_scores: cov={cov_score:.1f} cc={cc_score:.1f} type={type_score:.1f} loc={loc_score:.1f}')
print(f'score: {final:.2f}')
"
