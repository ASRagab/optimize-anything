#!/usr/bin/env bash
# Evaluator: cookbook_clarity
# Scores documentation/cookbook files on structure, actionability, specificity, and conciseness.
# Tuned for longer reference docs (cookbooks, guides) vs the tighter SKILL.md profile.
#
# Input:  JSON on stdin: {"candidate": "<text>"}
# Output: JSON on stdout: {"score": <float>, "structure": <float>,
#         "actionability": <float>, "specificity": <float>,
#         "conciseness": <float>, "feedback": [...]}
#
# Weights: structure=0.25, actionability=0.25, specificity=0.20, conciseness=0.30

set -euo pipefail

input_file=$(mktemp)
trap 'rm -f "$input_file"' EXIT
cat > "$input_file"

python3 - "$input_file" <<'PY'
import json
import re
import sys

WEIGHTS = {
    "structure": 0.25,
    "actionability": 0.25,
    "specificity": 0.20,
    "conciseness": 0.30,
}

try:
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        data = json.load(fh)
except json.JSONDecodeError:
    print(json.dumps({"score": 0.0, "error": "Input must be valid JSON"}))
    raise SystemExit(0)

candidate = str(data.get("candidate", ""))
if not candidate.strip():
    print(json.dumps({
        "score": 0.0,
        "structure": 0.0,
        "actionability": 0.0,
        "specificity": 0.0,
        "conciseness": 0.0,
        "feedback": ["Candidate is empty"],
    }))
    raise SystemExit(0)

lines = candidate.split("\n")
candidate_lower = candidate.lower()
feedback = []

# ---------------------------------------------------------------------------
# 1. Structure (weight 0.25)
# ---------------------------------------------------------------------------
structure_signals = []

# Frontmatter (optional for cookbooks — 0.5 baseline if missing)
has_frontmatter = candidate.lstrip().startswith("---")
if has_frontmatter:
    fm_end = candidate.find("---", candidate.find("---") + 3)
    has_frontmatter = fm_end > 0
structure_signals.append(1.0 if has_frontmatter else 0.5)

# Heading count and hierarchy (cookbook sweet spot: 6-20 headings)
headings = [l for l in lines if re.match(r"^#{1,4}\s", l)]
heading_count = len(headings)
if heading_count <= 20:
    heading_score = min(1.0, heading_count / 8.0)
elif heading_count <= 30:
    heading_score = max(0.5, 1.0 - (heading_count - 20) * 0.05)
else:
    heading_score = max(0.2, 0.5 - (heading_count - 30) * 0.03)
structure_signals.append(heading_score)
if heading_count < 3:
    feedback.append(f"Only {heading_count} headings found; add section headings for better scanability")

# Heading depth variety (has h2 and h3)
h2_count = sum(1 for h in headings if h.startswith("## "))
h3_count = sum(1 for h in headings if h.startswith("### "))
has_depth = 1.0 if (h2_count >= 1 and h3_count >= 1) else 0.4 if h2_count >= 1 else 0.0
structure_signals.append(has_depth)
if h3_count == 0:
    feedback.append("Use ### sub-headings to break up long sections")

# Bullet/numbered lists
list_items = sum(1 for l in lines if re.match(r"^\s*[-*]\s", l) or re.match(r"^\s*\d+\.\s", l))
list_score = min(1.0, list_items / 10.0)
structure_signals.append(list_score)
if list_items < 3:
    feedback.append("Add bullet or numbered lists for scannable instructions")

# Code blocks
code_block_count = candidate.count("```")
code_block_pairs = code_block_count // 2
code_score = min(1.0, code_block_pairs / 3.0)
structure_signals.append(code_score)
if code_block_pairs == 0:
    feedback.append("Include at least one code block with a concrete example")

# Section balance
heading_positions = [i for i, l in enumerate(lines) if re.match(r"^#{1,4}\s", l)]
if len(heading_positions) >= 2:
    section_lengths = []
    for idx in range(len(heading_positions)):
        start = heading_positions[idx]
        end = heading_positions[idx + 1] if idx + 1 < len(heading_positions) else len(lines)
        section_text = "\n".join(lines[start:end]).strip()
        section_lengths.append(len(section_text))
    if section_lengths:
        avg_section = sum(section_lengths) / len(section_lengths)
        max_section = max(section_lengths)
        if avg_section > 0:
            imbalance = max_section / avg_section
            balance_score = max(0.3, 1.0 - (imbalance - 1.5) * 0.15) if imbalance > 1.5 else 1.0
        else:
            balance_score = 0.5
    else:
        balance_score = 0.5
else:
    balance_score = 0.5
structure_signals.append(balance_score)

structure = sum(structure_signals) / len(structure_signals)

# ---------------------------------------------------------------------------
# 2. Actionability (weight 0.25)
# ---------------------------------------------------------------------------
actionability_signals = []

imperative_verbs = [
    "use", "run", "create", "add", "set", "configure", "check", "verify",
    "ensure", "start", "define", "choose", "select", "generate", "test",
    "validate", "write", "include", "avoid", "return", "pass", "pipe",
    "install", "call", "identify", "ask", "lock", "adapt",
]
imperative_hits = 0
for line in lines:
    stripped = line.strip().lstrip("-*0123456789.) ")
    first_word = stripped.split()[0].lower() if stripped.split() else ""
    if first_word in imperative_verbs:
        imperative_hits += 1
for verb in imperative_verbs:
    imperative_hits += len(re.findall(r"(?:^|\.\s+)" + verb + r"\s", candidate_lower, re.MULTILINE))
imperative_hits = min(imperative_hits, 40)
imperative_score = min(1.0, imperative_hits / 15.0)
actionability_signals.append(imperative_score)
if imperative_hits < 4:
    feedback.append("Use more imperative verbs (e.g., 'Run ...', 'Add ...', 'Check ...') for direct guidance")

numbered_steps = sum(1 for l in lines if re.match(r"^\s*\d+\.\s", l))
step_score = min(1.0, numbered_steps / 6.0)
actionability_signals.append(step_score)
if numbered_steps < 2:
    feedback.append("Add numbered steps (1. 2. 3.) for sequential procedures")

constraint_phrases = ["must", "should", "avoid", "do not", "don't", "never", "always", "required"]
constraint_hits = sum(candidate_lower.count(p) for p in constraint_phrases)
constraint_score = min(1.0, constraint_hits / 8.0)
actionability_signals.append(constraint_score)

task_phrases = ["how to", "steps", "step ", "workflow", "guide", "procedure", "checklist"]
task_hits = sum(1 for p in task_phrases if p in candidate_lower)
task_score = min(1.0, task_hits / 3.0)
actionability_signals.append(task_score)

outcome_phrases = [
    "you will", "you'll get", "this produces", "this returns", "this generates",
    "output:", "result:", "returns:", "produces:", "the result",
    "you should see", "expected output", "this gives",
]
outcome_hits = sum(1 for p in outcome_phrases if p in candidate_lower)
outcome_score = min(1.0, outcome_hits / 3.0)
actionability_signals.append(outcome_score)
if outcome_hits == 0:
    feedback.append("Describe expected outcomes (e.g., 'This returns ...', 'You will see ...')")

actionability = sum(actionability_signals) / len(actionability_signals)

# ---------------------------------------------------------------------------
# 3. Specificity (weight 0.20)
# ---------------------------------------------------------------------------
specificity_signals = []

inline_code = re.findall(r"`[^`]+`", candidate)
inline_code_clean = [c for c in inline_code if not c.startswith("```")]
inline_code_count = len(inline_code_clean)
inline_code_score = min(1.0, inline_code_count / 12.0)
specificity_signals.append(inline_code_score)
if inline_code_count < 3:
    feedback.append("Wrap file paths, commands, and parameter names in backticks for specificity")

path_pattern = r"(?:[./][\w\-./]+\.\w+|[\w\-]+/[\w\-./]+)"
path_hits = len(re.findall(path_pattern, candidate))
path_score = min(1.0, path_hits / 6.0)
specificity_signals.append(path_score)
if path_hits < 2:
    feedback.append("Reference specific file paths to anchor instructions in the codebase")

code_blocks = re.findall(r"```[\w]*\n(.*?)```", candidate, re.DOTALL)
non_empty_blocks = [b for b in code_blocks if b.strip()]
example_score = min(1.0, len(non_empty_blocks) / 3.0)
specificity_signals.append(example_score)
if len(non_empty_blocks) == 0:
    feedback.append("Add concrete code examples inside fenced code blocks")

named_refs = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", candidate)  # CamelCase
named_refs += re.findall(r"`\w+(?:-\w+)+`", candidate)  # kebab-case in backticks
named_ref_score = min(1.0, len(named_refs) / 6.0)
specificity_signals.append(named_ref_score)

specificity = sum(specificity_signals) / len(specificity_signals)

# ---------------------------------------------------------------------------
# 4. Conciseness (weight 0.30)
#    Cookbook sweet spot: 800-10000 chars (wider than SKILL.md's 800-6000)
# ---------------------------------------------------------------------------
conciseness_signals = []

length = len(candidate)
if length < 200:
    len_score = length / 200.0
    feedback.append("Content is too short; expand with more actionable detail")
elif length <= 800:
    len_score = 0.6 + 0.4 * ((length - 200) / 600.0)
elif length <= 10000:
    len_score = 1.0
elif length <= 14000:
    len_score = max(0.3, 1.0 - (length - 10000) / 6000.0)
    feedback.append("Content is getting long; trim or restructure to stay under 10K chars")
elif length <= 20000:
    len_score = max(0.05, 0.3 - (length - 14000) / 12000.0)
    feedback.append("Content is excessively long; aggressively cut or restructure")
else:
    len_score = 0.0
    feedback.append("HARD LIMIT: content exceeds 20K chars; must be drastically shortened")
conciseness_signals.append(len_score)

heading_texts = [h.strip().lstrip("#").strip().lower() for h in headings]
unique_headings = len(set(heading_texts))
if heading_count > 0:
    heading_uniqueness = unique_headings / heading_count
else:
    heading_uniqueness = 1.0
conciseness_signals.append(heading_uniqueness)
if heading_uniqueness < 0.8:
    feedback.append(f"Reduce heading redundancy ({heading_count} headings, {unique_headings} unique)")

filler_phrases = [
    "it is important to note that", "it should be noted that",
    "in order to", "as a matter of fact", "basically",
    "it is worth mentioning", "at the end of the day",
    "for all intents and purposes", "the fact that",
    "it goes without saying", "needless to say",
    "as you can see", "as mentioned above",
    "please note that", "keep in mind that",
]
filler_count = sum(candidate_lower.count(f) for f in filler_phrases)
filler_score = max(0.0, 1.0 - filler_count * 0.2)
conciseness_signals.append(filler_score)
if filler_count > 2:
    feedback.append(f"Remove filler phrases ({filler_count} found); prefer direct statements")

non_ws = len(re.sub(r"\s+", "", candidate))
density = non_ws / length if length > 0 else 0
if density >= 0.55 and density <= 0.80:
    density_score = 1.0
elif density < 0.55:
    density_score = density / 0.55
else:
    density_score = max(0.5, 1.0 - (density - 0.80) / 0.20)
conciseness_signals.append(density_score)

paragraphs = [p.strip() for p in re.split(r"\n\s*\n", candidate) if p.strip()]
if paragraphs:
    avg_para_len = sum(len(p) for p in paragraphs) / len(paragraphs)
    if avg_para_len <= 300:
        para_score = 1.0
    elif avg_para_len <= 600:
        para_score = max(0.4, 1.0 - (avg_para_len - 300) / 600.0)
    else:
        para_score = 0.3
        feedback.append("Break up long paragraphs for better readability")
else:
    para_score = 0.0
conciseness_signals.append(para_score)

raw_conciseness = sum(conciseness_signals) / len(conciseness_signals)
conciseness = min(raw_conciseness, len_score + 0.25) if len_score < 0.4 else raw_conciseness

# ---------------------------------------------------------------------------
# Weighted total
# ---------------------------------------------------------------------------
score = round(
    WEIGHTS["structure"] * structure
    + WEIGHTS["actionability"] * actionability
    + WEIGHTS["specificity"] * specificity
    + WEIGHTS["conciseness"] * conciseness,
    4,
)

score = max(0.0, min(1.0, score))

result = {
    "score": score,
    "structure": round(structure, 4),
    "actionability": round(actionability, 4),
    "specificity": round(specificity, 4),
    "conciseness": round(conciseness, 4),
    "feedback": feedback,
    "length": length,
    "heading_count": heading_count,
    "list_items": list_items,
    "code_block_pairs": code_block_pairs,
    "inline_code_count": inline_code_count,
    "imperative_hits": imperative_hits,
    "numbered_steps": numbered_steps,
}

print(json.dumps(result))
PY
