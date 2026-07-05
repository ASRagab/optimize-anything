#!/usr/bin/env bash
# Deterministic training scorer for the evaluator-generation benchmark.
# Input: {"candidate": "<SKILL.md text>"}
# Output: {"score": <0..1>, dimension scores, "feedback": [...]}

set -euo pipefail

input_file=$(mktemp)
trap 'rm -f "$input_file"' EXIT
cat > "$input_file"

python3 - "$input_file" <<'PY'
from __future__ import annotations

import json
import math
import re
import sys


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def contains_any(text: str, options: list[str]) -> bool:
    return any(option in text for option in options)


def ratio(hits: list[bool]) -> float:
    return sum(1 for hit in hits if hit) / max(len(hits), 1)


def length_score(text: str) -> float:
    length = len(text)
    if length < 700:
        return clamp(length / 700.0)
    if length <= 5200:
        return 1.0
    if length <= 7500:
        return clamp(1.0 - ((length - 5200) / 3500.0))
    return 0.25


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
if not candidate.strip():
    print(json.dumps({"score": 0.0, "error": "Candidate must not be empty"}))
    raise SystemExit(0)

lower = candidate.lower()
feedback: list[str] = []
code_blocks = re.findall(r"```[a-zA-Z0-9_-]*\n(.*?)```", candidate, re.DOTALL)

contract_completeness = ratio([
    "candidate" in lower,
    "json" in lower and contains_any(lower, ["stdin", "post body", "http post"]),
    '"score"' in candidate or "`score`" in candidate or "score output" in lower,
    contains_any(lower, ["float", "numeric", "finite", "[0,1]", "[0, 1]"]),
    contains_any(lower, ["feedback", "diagnostic", "dimension", "reasoning"]),
    contains_any(lower, ["dataset", "example"]),
])
if contract_completeness < 0.85:
    feedback.append("Clarify candidate input, numeric score output, score range, and diagnostic side fields.")

runnable_examples = ratio([
    bool(code_blocks),
    "optimize-anything generate-evaluator" in lower,
    "echo" in lower and "candidate" in lower,
    contains_any(lower, ["python3", "bash", "--evaluator-command"]),
    "--objective" in lower,
])
if runnable_examples < 0.8:
    feedback.append("Add copy-pasteable commands that generate an evaluator and test it with a JSON payload.")

feedback_quality = ratio([
    contains_any(lower, ["feedback", "diagnostic", "reasoning"]),
    contains_any(lower, ["dimension", "quality_dimensions", "subscore"]),
    contains_any(lower, ["reflection", "weak", "improve"]),
    contains_any(lower, ["hard constraint", "constraint failure", "safety gate"]),
    contains_any(lower, ["customize", "scoring logic", "rubric"]),
])
if feedback_quality < 0.8:
    feedback.append("Explain how evaluators return actionable diagnostics for reflection, not just a scalar score.")

calibration_guidance = ratio([
    contains_any(lower, ["0.3-0.7", "0.3 to 0.7", "0.85"]),
    contains_any(lower, ["discrimination", "non-discriminating", "too easy"]),
    contains_any(lower, ["baseline", "threshold", "score range"]),
    contains_any(lower, ["test", "validate"]),
    contains_any(lower, ["edge case", "malformed", "empty"]),
])
if calibration_guidance < 0.65:
    feedback.append("Add calibration guidance for weak or non-discriminating evaluators.")

structure = ratio([
    candidate.lstrip().startswith("---"),
    lower.count("\n## ") >= 4,
    lower.count("\n### ") >= 2,
    candidate.count("- ") >= 6,
    len(code_blocks) >= 2,
])
if structure < 0.8:
    feedback.append("Use frontmatter, section headings, lists, and fenced examples for scanability.")

conciseness = length_score(candidate)
if conciseness < 0.8:
    feedback.append("Keep the guidance concise enough to remain usable as a skill file.")

score = (
    contract_completeness * 0.28
    + runnable_examples * 0.22
    + feedback_quality * 0.20
    + calibration_guidance * 0.16
    + structure * 0.08
    + conciseness * 0.06
)
score = clamp(score)
if not math.isfinite(score):
    score = 0.0
if not feedback:
    feedback.append("Strong baseline; look for sharper calibration, held-out validation, or scorer-debugging guidance.")

print(json.dumps({
    "score": round(score, 4),
    "contract_completeness": round(contract_completeness, 4),
    "runnable_examples": round(runnable_examples, 4),
    "feedback_quality": round(feedback_quality, 4),
    "calibration_guidance": round(calibration_guidance, 4),
    "structure": round(structure, 4),
    "conciseness": round(conciseness, 4),
    "feedback": feedback[:5],
}))
PY
