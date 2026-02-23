#!/usr/bin/env bash
# Simple evaluator: scores based on candidate length
input=$(cat)
candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")
length=${#candidate}
echo "{\"score\": 0.${length}, \"length\": $length}"
