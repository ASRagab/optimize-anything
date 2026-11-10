#!/usr/bin/env bash
# Verification evaluator (command protocol: JSON on stdin, JSON on stdout).
# Scores 0.9 when the candidate contains the stub's marker, else 0.2, so a
# proposer-made candidate is distinguishable from the seed.
# Also appends each payload to $VERIFY_EVAL_LOG when that is set.
set -euo pipefail
payload=$(cat)
if [[ -n "${VERIFY_EVAL_LOG:-}" ]]; then printf '%s\n' "$payload" >> "$VERIFY_EVAL_LOG"; fi
if [[ "$payload" == *"VERIFY-MARKER-7f3a"* ]]; then
  echo '{"score": 0.9, "reasoning": "marker present"}'
else
  echo '{"score": 0.2, "reasoning": "marker absent; add the line VERIFY-MARKER-7f3a"}'
fi
