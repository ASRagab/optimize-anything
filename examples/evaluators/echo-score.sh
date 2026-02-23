#!/bin/bash
# echo-score.sh — Minimal evaluator that returns a deterministic score.
#
# Input (stdin): JSON with "candidate" field
# Output (stdout): JSON with "score" and "sideInfo"
#
# Scoring: length-based heuristic (longer candidates score higher, capped at 1.0)

read input
candidate=$(echo "$input" | jq -r '.candidate // empty')

if [ -z "$candidate" ]; then
  echo '{"score": 0, "sideInfo": {"error": "no candidate provided"}}'
  exit 0
fi

length=${#candidate}
# Score scales with length: 100 chars = 0.5, 200+ chars = ~1.0
score=$(awk "BEGIN { printf \"%.4f\", $length / ($length + 200) }")
echo "{\"score\": $score, \"sideInfo\": {\"length\": $length}}"
