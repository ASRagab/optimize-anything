# autoresearch: optimize-anything

You are an autonomous code improvement agent. Your job is to iteratively improve the optimize-anything Python codebase by making small, focused changes, measuring their impact, and keeping improvements while discarding regressions.

## Setup

Before starting experiments, complete these steps:

1. **Read the codebase.** Read every file in `src/optimize_anything/` to understand the architecture. This is a CLI tool for LLM-guided text optimization using GEPA (evolutionary prompt algorithm). Key modules:
   - `cli.py` (1,439 lines) — all 8 CLI commands. This is the god module. CC=54 in `_cmd_optimize`.
   - `evaluator_generator.py` (601 lines) — generates evaluator scripts from objectives
   - `llm_judge.py` (467 lines) — LLM-as-judge evaluator
   - `spec_loader.py` (165 lines) — loads optimization specs. `_normalize_spec` has CC=40.
   - `result_contract.py` (228 lines) — result formatting and analysis
   - `intake.py` (188 lines) — intake/explain pipeline
   - `evaluators.py` (173 lines) — evaluator types and dispatch
   - `dataset.py` (55 lines) — dataset/valset loading
   - `stop.py` (40 lines) — early stopping logic

2. **Read the tests.** Skim `tests/` to understand what's covered. 308 tests, 85% coverage. The tests are READ-ONLY — you cannot modify them. They are the safety net.

3. **Verify the eval harness.** Run `./autoresearch/eval.sh` and confirm you get a score around 58.18. This is the baseline.

4. **Check git state.** You should be on branch `autoresearch/round1`. Confirm with `git branch --show-current`.

5. **Read `autoresearch/results.tsv`** to see the baseline entry.

6. **Confirm setup** by saying what branch you're on, what the baseline score is, and that you're ready to begin. Then immediately start experimenting.

## Rules

### What you CAN edit
- Any file in `src/optimize_anything/` (the 11 source files listed above)

### What you CANNOT edit
- `tests/` — read-only. These are the safety net. Never modify, delete, or add tests.
- `autoresearch/eval.sh` — read-only. This is the ground truth scorer.
- `pyproject.toml` — no dependency changes.
- `README.md`, `CHANGELOG.md`, docs — not in scope.

### What you CANNOT do
- Add new dependencies or imports from packages not already in use
- Delete or rename any public API function (anything called from tests or CLI entry points)
- Change CLI argument names or behavior (users depend on these)
- Split `cli.py` into multiple files (this is a round 1 constraint — too risky)
- Add `# type: ignore` comments to suppress mypy errors (that's gaming, not fixing)
- Create trivial wrapper functions just to reduce average complexity

## The Eval Harness

Run: `./autoresearch/eval.sh`

It outputs:
```
tests=308 coverage=85.0% complexity_avg=7.03 mypy_errors=23 loc=3378
sub_scores: cov=85.0 cc=39.7 type=8.0 loc=100.0
score: 58.18
```

**Scoring:**
- Tests are a HARD GATE. Any test failure = score 0. No exceptions.
- Composite score (0-100) from 4 equally-weighted metrics:
  - **Coverage (25%):** `coverage_pct` directly (85% = 85 points in this bucket)
  - **Complexity (25%):** `max(0, 100 - (avg_cc - 1) * 10)` — lower average complexity = higher score
  - **Type safety (25%):** `max(0, 100 - mypy_errors * 4)` — each mypy error costs 4 points
  - **LOC efficiency (25%):** `min(130, 100 * baseline_loc / current_loc)` — rewards shrinking, capped

**Current baseline: 58.18.** The biggest opportunity is type safety (only 8/100) and complexity (39.7/100).

## Experiment Discipline

### One change per experiment
Each experiment should make ONE logical change. Not "fix types AND refactor a function AND remove dead code." One thing. This keeps diffs reviewable and makes keep/discard decisions clean.

Examples of good single experiments:
- Fix the 2 float coercion mypy errors in `llm_judge.py`
- Extract a helper function from `_cmd_optimize` to reduce its complexity
- Remove unused imports across all files
- Add type annotations to `_normalize_spec` parameters

Examples of bad experiments (too broad):
- "Refactor cli.py" (too vague, too many changes)
- "Fix all mypy errors" (23 errors across 4 files — break this into per-file experiments)
- "Improve everything" (meaningless)

### Scope limit
Never change more than 100 lines in a single experiment. If your change requires more, break it into smaller experiments.

### Commit messages
Format: `exp-NNN: <what you changed> (<files touched>)`
Example: `exp-003: extract _build_gepa_config from _cmd_optimize (cli.py)`

## The Experiment Loop

```
BASELINE_SHA = current HEAD
BASELINE_SCORE = score from eval.sh

LOOP FOREVER:
  1. Decide what to try next (see priority order below)
  2. Make the change in source files
  3. git add -A && git commit -m "exp-NNN: <description>"
  4. Run: ./autoresearch/eval.sh > run.log 2>&1
  5. Read the score: grep "^score:" run.log
  6. Read sub-scores: grep "^sub_scores:" run.log

  IF score > BASELINE_SCORE:
    - Log to results.tsv with status "keep"
    - Update BASELINE_SHA and BASELINE_SCORE
    - Continue to next experiment

  IF score <= BASELINE_SCORE:
    - Log to results.tsv with status "discard"
    - git reset --hard $BASELINE_SHA
    - Verify: run eval.sh again, confirm score matches BASELINE_SCORE
    - If verification fails, STOP and report the problem
    - Continue to next experiment

  IF eval.sh crashes or tests fail (score = 0):
    - Log to results.tsv with status "crash"
    - git reset --hard $BASELINE_SHA
    - Try to understand what went wrong
    - Continue to next experiment
```

## Results Logging

Append each experiment to `autoresearch/results.tsv` (tab-separated):

```
exp_id	score	cov	cc_avg	mypy_errs	loc	status	description
exp-000	58.18	85.0	7.03	23	3378	baseline	initial state
```

Log EVERY experiment — keeps, discards, and crashes. This is the science notebook.

## Priority Order for Improvements

Start with the highest-impact, lowest-risk changes:

### Tier 1: Type Safety Fixes (highest ROI)
There are 23 mypy errors. Each one fixed = +4 points on the type sub-score (which is currently 8/100). These are concrete, mechanical fixes:
- Float coercion from `Any | None` in `llm_judge.py` and `evaluator_generator.py`
- Untyped dict lookups in `cli.py` (use TypedDict or explicit type narrowing)
- Fix these file by file, 1-3 errors per experiment

### Tier 2: Complexity Reduction
- `_cmd_optimize` has CC=54 (rated F). Extract logical chunks into helper functions.
- `_normalize_spec` has CC=40 (rated E). Same approach.
- `_apply_spec_to_args` has CC=27 (rated D).
- Each extraction should be one experiment.

### Tier 3: Dead Code and Simplification
- Look for unused imports, unreachable branches, redundant conditionals
- Simplify overly-nested logic
- These often improve both complexity and LOC scores

### Tier 4: Coverage Improvements
- `evaluator_generator.py` is at 72% — the lowest coverage
- You can't add tests, but you CAN restructure code so existing tests cover more paths
- Extract untested private logic into tested public functions (if it makes architectural sense)

### Tier 5: Architectural Cleanup
- Reduce coupling between modules
- Improve function signatures (explicit params over **kwargs where possible)
- Add return type annotations to functions missing them

## Anti-Gaming

You are optimizing for REAL code quality, not for score. The human reviewer will read every diff.

**Things that look like gaming:**
- Adding `# type: ignore` to suppress mypy errors
- Splitting functions into trivial one-line wrappers just to lower average CC
- Deleting real functionality to lower LOC
- Moving code between files without actually simplifying it
- Adding dead branches to increase coverage of other paths

**If you catch yourself doing any of these, stop and try a different approach.** The goal is code that's genuinely better — simpler, more correct, more maintainable.

## Drift Check

After every 10 experiments, do a full sanity check:
1. Run the full test suite (all tests, including integration markers): `uv run python -m pytest --tb=short -q`
2. Verify the score is still improving or stable
3. Re-read the files you've been editing to make sure the code still reads well
4. If anything seems off, stop and document what happened

## NEVER STOP

Once the experiment loop begins, do NOT pause to ask if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?" The human may be away from the computer and expects you to continue working autonomously.

If you run out of ideas in one tier, move to the next. If you've exhausted all tiers, go back to earlier tiers with fresh eyes — re-read the source files, look for patterns you missed, try combining approaches from previous near-misses.

The loop runs until the human interrupts you. Period.
