#!/usr/bin/env bash
# Plugin evaluation harness for optimize-anything as a Claude Code plugin.
#
# Usage:
#   ./scripts/plugin_eval.sh [scenario]
#
# Scenarios:
#   budget    - Lightweight budget estimation (no LLM calls)
#   analyze   - Single LLM call to analyze artifact quality dimensions
#   validate  - Cross-provider validation (2+ providers)
#   quick     - Full optimization loop (most expensive)
#   all       - Run all scenarios sequentially
#
# Requirements:
#   - claude CLI installed and authenticated
#   - OPENAI_API_KEY and/or ANTHROPIC_API_KEY set
#   - This script must be run from the repo root

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT"
RESULTS_DIR="$REPO_ROOT/runs/plugin-eval"
SEED_FILE="$REPO_ROOT/runs/zo-eval/seed.txt"

SCENARIO="${1:-all}"

mkdir -p "$RESULTS_DIR"

# Common claude flags
CLAUDE_BASE=(
  claude -p
  --plugin-dir "$PLUGIN_DIR"
  --output-format json
  --allowedTools "Bash Read Write Edit Glob Grep"
  --max-budget-usd 0.50
)

timestamp() {
  date -u +"%Y%m%dT%H%M%SZ"
}

run_scenario() {
  local name="$1"
  local prompt="$2"
  local outfile="$RESULTS_DIR/${name}-$(timestamp).json"

  echo "=== Scenario: $name ==="
  echo "Prompt: $prompt"
  echo "Output: $outfile"
  echo ""

  local start_time
  start_time=$(date +%s)

  # Run claude in print mode with the plugin loaded
  "${CLAUDE_BASE[@]}" "$prompt" > "$outfile" 2>"$RESULTS_DIR/${name}-stderr.log" || true

  local end_time
  end_time=$(date +%s)
  local elapsed=$(( end_time - start_time ))

  echo "Completed in ${elapsed}s"
  echo "---"

  # Quick validation: check if output is valid JSON
  if jq empty "$outfile" 2>/dev/null; then
    echo "Output: valid JSON"
    # Extract cost if available
    jq -r '.cost_usd // "n/a"' "$outfile" 2>/dev/null || true
  else
    echo "Output: not valid JSON (check file manually)"
  fi
  echo ""
}

scenario_budget() {
  run_scenario "budget" \
    "Use the optimize-anything plugin to estimate a budget for the seed file at $SEED_FILE. Run: optimize-anything budget $SEED_FILE"
}

scenario_analyze() {
  run_scenario "analyze" \
    "Use the optimize-anything plugin to analyze the artifact at $SEED_FILE for quality dimensions. Run: optimize-anything analyze $SEED_FILE --judge-model openai/gpt-4o-mini --objective 'Score the quality of this system prompt'"
}

scenario_validate() {
  run_scenario "validate" \
    "Use the optimize-anything plugin to validate the artifact at $SEED_FILE across multiple providers. Run: optimize-anything validate $SEED_FILE --providers openai/gpt-4o-mini anthropic/claude-haiku-4-5-20251001 --objective 'Score the quality and clarity of this system prompt'"
}

scenario_quick() {
  run_scenario "quick" \
    "Use the optimize-anything plugin to quickly optimize the seed at $SEED_FILE. Run: optimize-anything optimize $SEED_FILE --judge-model openai/gpt-4o-mini --objective 'Improve clarity and specificity of this system prompt' --budget 5 --model openai/gpt-4o-mini --output $RESULTS_DIR/quick-best.txt"
}

case "$SCENARIO" in
  budget)   scenario_budget ;;
  analyze)  scenario_analyze ;;
  validate) scenario_validate ;;
  quick)    scenario_quick ;;
  all)
    scenario_budget
    scenario_analyze
    scenario_validate
    scenario_quick
    echo "=== All scenarios complete ==="
    echo "Results in: $RESULTS_DIR"
    ;;
  *)
    echo "Unknown scenario: $SCENARIO"
    echo "Valid: budget, analyze, validate, quick, all"
    exit 1
    ;;
esac
