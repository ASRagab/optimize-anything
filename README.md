# optimize-anything

LLM-guided optimization for text artifacts using an iterative propose-evaluate-reflect loop with a bring-your-own evaluator.

## Overview

optimize-anything takes a seed artifact (prompt, code snippet, config, etc.), evaluates it against your custom scoring function, then uses an LLM to propose improvements. The loop runs until a budget is exhausted or a stop condition is met.

**Core loop:** seed -> evaluate -> propose mutation -> evaluate -> reflect -> repeat

Key features:
- **BYO evaluator** -- shell commands or HTTP endpoints
- **Powered by gepa** -- evolutionary search with LLM-guided mutations
- **CLI** -- run optimizations from the terminal
- **Evaluator generator** -- auto-generate starter evaluator scripts

## Install

**Claude Code plugin** — skills + `/optimize` command inside Claude Code:

```bash
claude plugin add https://github.com/ASRagab/optimize-anything
```
> Requires [uv](https://docs.astral.sh/uv/) and Python >= 3.10.

**Terminal CLI** — installs the `optimize-anything` command in your shell:

```bash
# One-liner (installs uv if needed):
curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash

# Or directly with uv:
uv tool install git+https://github.com/ASRagab/optimize-anything
```
> Plugin and CLI are independent -- install either or both.

**From source** (for development):

```bash
git clone https://github.com/ASRagab/optimize-anything.git && cd optimize-anything
uv sync
```

See [install.md](install.md) for platform-specific setup and troubleshooting.

## Quickstart

### CLI

```bash
# Create a seed file
echo "Write a haiku about the ocean" > seed.txt

# Create an evaluator (stdin JSON -> stdout JSON with score)
cat > eval.sh << 'EVAL'
#!/usr/bin/env bash
python3 -c '
import json
import re
import sys

payload = json.load(sys.stdin)
candidate = str(payload.get("candidate", ""))
text = candidate.lower()

checks = {
    "mentions_haiku": bool(re.search(r"\bhaiku\b", text)),
    "mentions_ocean": bool(re.search(r"\bocean\b", text)),
    "requires_575": bool(re.search(r"5\s*-\s*7\s*-\s*5|5-7-5", text)),
    "requires_three_lines": bool(
        re.search(r"exactly\s*(3|three)\s*lines|three\s*lines", text)
    ),
    "forbids_extra_text": bool(
        re.search(r"no title|no extra text|only.*poem|plain text", text)
    ),
}

weights = {
    "mentions_haiku": 0.15,
    "mentions_ocean": 0.15,
    "requires_575": 0.35,
    "requires_three_lines": 0.2,
    "forbids_extra_text": 0.15,
}

score = sum(weights[name] for name, ok in checks.items() if ok)
score = round(min(score, 1.0), 4)

print(
    json.dumps(
        {
            "score": score,
            "checks_passed": sum(1 for ok in checks.values() if ok),
            **checks,
        }
    )
)
'
EVAL
chmod +x eval.sh

# Validate evaluator manually before optimize
echo '{"candidate":"test"}' | bash ./eval.sh

# Run optimization
ANTHROPIC_API_KEY=sk-... uv run optimize-anything optimize seed.txt \
  --evaluator-command bash ./eval.sh \
  --budget 10 \
  --output result.txt
```

This evaluator is intentionally non-constant: candidates that add concrete haiku constraints
(5-7-5, exactly 3 lines, plain text only) score higher than vague prompts, so optimization
can move away from the original seed.

The optimized artifact is written to `result.txt`. CLI stdout returns a canonical
JSON summary (`best_artifact`, `total_metric_calls`, `score_summary`,
`top_diagnostics`, `plateau_guidance`, optional `evaluator_failure_signal`).

If your evaluator script is under `artifacts/`, use one of these path-safe forms:

```bash
# Option A: full relative script path
--evaluator-command bash artifacts/eval.sh

# Option B: set evaluator working directory
--evaluator-command bash eval.sh --evaluator-cwd artifacts
```

## Evaluator Contract

Your evaluator receives JSON on stdin and must return JSON on stdout:

**Input (stdin):**
```json
{
  "candidate": "the text artifact being scored"
}
```

**Output (stdout):**
```json
{
  "score": 0.75,
  "length": 42,
  "notes": "optional diagnostic text"
}
```

- `score` (required): float, higher is better
- Any additional fields become side information fed back to gepa's reflection LM

See [evaluator-cookbook.md](evaluator-cookbook.md) for full recipes.

## Evaluator Runtime vs Pattern

Two similarly named fields serve different purposes:

| Field | What it answers | Allowed values | What it affects |
|---|---|---|---|
| `execution_mode` (runtime type) | How the evaluator is executed | `command`, `http` | CLI wiring, infra, and failure modes |
| `evaluation_pattern` (scoring strategy) | How scoring logic is designed | `verification`, `judge`, `simulation`, `composite` | Evaluator design intent and intake metadata |

Example (full intake spec):

```json
{
  "artifact_class": "prompt",
  "execution_mode": "command",
  "evaluation_pattern": "judge",
  "quality_dimensions": [
    {"name": "clarity", "weight": 0.5},
    {"name": "constraint_adherence", "weight": 0.5}
  ],
  "hard_constraints": ["must be under 500 tokens"],
  "evaluator_cwd": "/path/to/project"
}
```

`execution_mode` decides whether you run `--evaluator-command ...` or `--evaluator-url ...`.
`evaluation_pattern` does not change transport; it describes the evaluator's scoring approach.

## CLI Commands

### optimize

```bash
uv run optimize-anything optimize <seed_file> [options]
```

| Flag | Description | Default |
|---|---|---|
| `seed_file` | Path to seed artifact file | (required) |
| `--evaluator-command <cmd...>` | Shell command evaluator | -- |
| `--evaluator-cwd <path>` | Working directory for evaluator command | current process cwd |
| `--evaluator-url <url>` | HTTP POST evaluator URL | -- |
| `--intake-json <json-string>` | Inline evaluator intake JSON (validated) | -- |
| `--intake-file <path>` | Path to evaluator intake JSON file (validated) | -- |
| `--objective <text>` | Natural language objective | -- |
| `--background <text>` | Domain knowledge/constraints | -- |
| `--budget <n>` | Max evaluator invocations | 100 |
| `--output, -o <file>` | Write best candidate to file | stdout |

If intake is provided, `execution_mode` is used to decide which evaluator source flag is required when neither `--evaluator-command` nor `--evaluator-url` is set. Explicit evaluator flags always win if both explicit flags and intake are supplied.
`--output` must be a file path (not an existing directory).

### explain

```bash
uv run optimize-anything explain <seed_file> [--objective <text>]
```

Preview what optimization would do for a given seed artifact.

### budget

```bash
uv run optimize-anything budget <seed_file>
```

Get a recommended evaluation budget based on the seed artifact length.

### generate-evaluator

```bash
uv run optimize-anything generate-evaluator <seed_file> --objective <text> [--evaluator-type command|http] [--intake-json <json>] [--intake-file <path>]
```

Generate a starter evaluator script from a seed artifact and objective. Outputs to stdout.

| Flag | Description | Default |
|---|---|---|
| `seed_file` | Path to seed artifact file | (required) |
| `--objective <text>` | Natural language optimization objective | (required) |
| `--evaluator-type` | Script type: `command` (bash) or `http` (Python) | inferred from intake or `command` |
| `--intake-json <json>` | Inline intake spec JSON | -- |
| `--intake-file <path>` | Path to intake spec JSON file | -- |

### intake

```bash
uv run optimize-anything intake [options]
```

Normalize and validate an evaluator intake specification. Outputs canonical JSON to stdout.

| Flag | Description | Default |
|---|---|---|
| `--artifact-class <text>` | Type of artifact being optimized | `general_text` |
| `--execution-mode` | Evaluator transport: `command` or `http` | `command` |
| `--evaluation-pattern` | Scoring strategy: `verification`, `judge`, `simulation`, `composite` | `judge` |
| `--hard-constraint <text>` | Hard constraint (repeatable) | -- |
| `--evaluator-cwd <path>` | Working directory for evaluator | -- |
| `--intake-json <json>` | Inline intake spec JSON (mutually exclusive with flags) | -- |
| `--intake-file <path>` | Path to intake spec JSON file (mutually exclusive with flags) | -- |

## Architecture

```
src/optimize_anything/
  __init__.py              # Public API re-exports
  evaluators.py            # Command and HTTP evaluator factories
  evaluator_generator.py   # Generate evaluator scripts from seed + objective
  cli.py                   # CLI entry point (argparse)
  intake.py                # Intake schema normalization
  result_contract.py       # Canonical optimize summary output
  __main__.py              # python -m support

commands/
  optimize.md              # /optimize command definition

skills/
  generate-evaluator/      # Evaluator generation skill
  optimization-guide/      # Optimization workflow guide

examples/
  evaluators/              # Sample evaluator scripts
  seeds/                   # Sample seed artifacts
```

## Programmatic API

```python
from optimize_anything import optimize_anything, command_evaluator
from gepa.optimize_anything import GEPAConfig, EngineConfig

eval_fn = command_evaluator(["bash", "eval.sh"])
config = GEPAConfig(engine=EngineConfig(max_metric_calls=20))

result = optimize_anything(
    seed_candidate="initial text",
    evaluator=eval_fn,
    objective="maximize clarity",
    config=config,
)

print(result.best_candidate)
```

## Generating Evaluators

If you do not have an evaluator, optimize-anything can generate one:

```python
from optimize_anything.evaluator_generator import generate_evaluator_script

script = generate_evaluator_script(
    seed="Your seed artifact",
    objective="maximize clarity",
    evaluator_type="command",  # or "http"
)
```

This produces a bash script (or Python HTTP server) that you can customize.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ANTHROPIC_API_KEY missing` | Set `ANTHROPIC_API_KEY` in your environment |
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| `Seed file not found` | Check the seed file path is correct |
| `Evaluator command failed` | Manually run `echo '{"candidate":"test"}' | <your evaluator command>` and verify it exits 0 with valid JSON |
| `Evaluator script not found` | Use a full relative script path (for example, `artifacts/eval.sh`) or set `--evaluator-cwd artifacts` |
| `Invalid JSON` from evaluator | Ensure evaluator writes only JSON to stdout (logs go to stderr) |
| `Error: --output must be a file path` | Pass a filename like `artifacts/result.txt`, not a directory path like `artifacts/` |

## Uninstall

**CLI** (`optimize-anything` command):

```bash
uv tool uninstall optimize-anything
```

**Plugin:**

```bash
claude plugin remove optimize-anything
```

## Links

- [Installation Guide](install.md)
- [Evaluator Cookbook](evaluator-cookbook.md)
- [Examples](examples/)
