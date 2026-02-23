#!/usr/bin/env bash
# Simple evaluator: scores based on candidate length (normalized to 0-1).
# Input:  JSON on stdin: {"candidate": "<text>"}
# Output: JSON on stdout: {"score": <float>, "length": <int>}
#
# Score formula: 1 - exp(-length/100)
#   length=0   -> 0.0
#   length=100 -> 0.6321
#   length=500 -> 0.9933
python3 -c "
import json, sys, math
data = json.load(sys.stdin)
candidate = data['candidate']
length = len(candidate)
score = round(1.0 - math.exp(-length / 100.0), 4)
print(json.dumps({'score': score, 'length': length}))
"
