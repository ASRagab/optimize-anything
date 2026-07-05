#!/usr/bin/env bash
# Deterministic held-out scorer for the evaluator-generation benchmark.
# Uses a different rubric from the training scorer to discourage scorer gaming.

set -euo pipefail

input_file=$(mktemp)
trap 'rm -f "$input_file"' EXIT
cat > "$input_file"

python3 - "$input_file" <<'PY'
from __future__ import annotations

import json
import re
import sys


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def any_of(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def score_hits(hits: list[bool]) -> float:
    return sum(1 for hit in hits if hit) / max(len(hits), 1)


try:
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        payload = json.load(fh)
except json.JSONDecodeError:
    print(json.dumps({"score": 0.0, "error": "Input must be valid JSON"}))
    raise SystemExit(0)

if "candidate" not in payload or not isinstance(payload["candidate"], str):
    print(json.dumps({"score": 0.0, "error": "Payload must include string field 'candidate'"}))
    raise SystemExit(0)

candidate = payload["candidate"]
lower = candidate.lower()
blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", candidate, re.DOTALL)
feedback: list[str] = []

contract_safety = score_hits([
    any_of(lower, ["invalid json", "malformed", "empty"]),
    any_of(lower, ["score range", "[0,1]", "[0, 1]", "finite"]),
    any_of(lower, ["stderr", "exit", "return code", "timeout"]),
    any_of(lower, ["candidate", "example"]),
])
if contract_safety < 0.5:
    feedback.append("Held-out check: include failure handling for malformed payloads and invalid scores.")

pattern_coverage = score_hits([
    "judge" in lower,
    "command" in lower,
    "http" in lower,
    "composite" in lower,
    "dataset" in lower or "valset" in lower,
])
if pattern_coverage < 0.8:
    feedback.append("Held-out check: cover judge, command, HTTP, composite, and dataset-aware evaluators.")

reviewability = score_hits([
    any_of(lower, ["baseline", "acceptance", "threshold"]),
    any_of(lower, ["discrimination", "too easy", "0.85"]),
    any_of(lower, ["validate", "cross-check", "held-out"]),
    len(blocks) >= 2,
])
if reviewability < 0.5:
    feedback.append("Held-out check: explain how maintainers decide whether an evaluator is good enough.")

workflow_fit = score_hits([
    candidate.lstrip().startswith("---"),
    lower.count("\n## ") >= 4,
    "--objective" in lower,
    "optimize-anything" in lower,
])
if workflow_fit < 0.75:
    feedback.append("Held-out check: preserve skill structure and optimize-anything command context.")

brevity = 1.0
if len(candidate) > 7000:
    brevity = 0.5
    feedback.append("Held-out check: guidance is long; tighten before accepting.")
elif len(candidate) < 700:
    brevity = 0.4
    feedback.append("Held-out check: guidance is too short to be operational.")

score = clamp(
    contract_safety * 0.25
    + pattern_coverage * 0.25
    + reviewability * 0.20
    + workflow_fit * 0.20
    + brevity * 0.10
)

print(json.dumps({
    "score": round(score, 4),
    "contract_safety": round(contract_safety, 4),
    "pattern_coverage": round(pattern_coverage, 4),
    "reviewability": round(reviewability, 4),
    "workflow_fit": round(workflow_fit, 4),
    "brevity": round(brevity, 4),
    "feedback": feedback[:5],
}))
PY
