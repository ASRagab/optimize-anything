# optimize-anything — Implementation Plan

> Optimize any text artifact: prompts, skills, configs, code, agent architectures.
> Inspired by [GEPA optimize_anything](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/).

## 1. Overview

A TypeScript/Bun tool that runs iterative **propose → evaluate → reflect** cycles on any text artifact. Ships as:

1. **MCP server** usable by Claude Code, OpenClaw, or any MCP client
2. **OpenClaw skill** with SKILL.md + CLI wrapper
3. **Standalone CLI** for scripting

One optimizer core, two thin adapters. The evaluator is the hard part — without a real scoring function, the optimizer hallucinates improvements.

## 2. Architecture

```
┌─────────────────────────────────────────────────┐
│                   MCP Server                     │
│  (stdio transport — works with Claude Code +     │
│   OpenClaw mcporter)                             │
├─────────────────────────────────────────────────┤
│                                                  │
│  Tools exposed:                                  │
│    optimize        — run optimization loop       │
│    optimize_status — check running/completed run │
│    optimize_stop   — early-stop a run            │
│                                                  │
├─────────────────────────────────────────────────┤
│              optimizer-core                       │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ Proposer   │→│ Evaluator  │→│ Reflector    │ │
│  │ (LLM call) │  │ (user fn)  │  │ (LLM call)  │ │
│  └───────────┘  └───────────┘  └──────────────┘ │
│       ↑                              │           │
│       └──────── loop ←───────────────┘           │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ RunState: candidates, scores, ASI, budget │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
         │                        │
    Claude Code              OpenClaw skill
    (MCP client)             (mcporter / native)
```

## 3. Core Package Design

### Key Interfaces

```typescript
// What the user provides
interface OptimizeRequest {
  // Starting point — provide one or both
  seedCandidate?: string;          // existing artifact text
  objective?: string;              // natural language description of what to create/improve

  // Evaluation
  evaluator: EvaluatorConfig;      // how to score candidates

  // Budget
  maxIterations?: number;          // default: 10
  maxTokens?: number;              // total LLM token budget
  maxTimeSeconds?: number;         // wall clock limit
  targetScore?: number;            // stop early if reached

  // Proposer config
  proposerModel?: string;          // default: claude-sonnet-4-6
  temperature?: number;            // default: 0.7 for diversity

  // Guardrails
  constraints?: string[];          // natural language constraints ("never remove error handling")
  regressionTests?: RegressionTest[];  // must-pass checks
  bannedPatterns?: string[];       // regex patterns that must not appear in candidates
}

interface EvaluatorConfig {
  // One of these:
  command?: string;                // shell command: receives candidate via stdin, returns JSON {score, diagnostics?}
  scriptPath?: string;             // path to evaluator script
  httpEndpoint?: string;           // POST candidate, get back {score, diagnostics?}
  builtIn?: string;                // "prompt-quality" | "code-lint" | "test-pass-rate"

  // Evaluator receives candidate text, must return:
  // { score: number, diagnostics?: Record<string, any> }
}

interface RegressionTest {
  name: string;
  command: string;                 // must exit 0 for candidate to pass
}

interface OptimizeResult {
  bestCandidate: string;
  bestScore: number;
  iterations: number;
  history: CandidateRecord[];
  totalTokens: number;
  totalTimeSeconds: number;
  stoppedReason: "target_reached" | "budget_exhausted" | "max_iterations" | "manual_stop" | "regression_fail";
}

interface CandidateRecord {
  iteration: number;
  candidate: string;
  score: number;
  diagnostics?: Record<string, any>;
  proposerReasoning: string;       // why this mutation was proposed
  reflectorNotes: string;          // what the reflector observed
  diff: string;                    // unified diff from previous best
}
```

### Modules

```
src/
  core/
    optimizer.ts        — main loop: propose → evaluate → reflect
    proposer.ts         — LLM-based candidate generation
    evaluator.ts        — evaluator runner (shell, http, built-in)
    reflector.ts        — LLM-based reflection on eval results → ASI
    budget.ts           — token/time/iteration tracking + early stop
    state.ts            — RunState management, history, best tracking
    constraints.ts      — regression test runner, banned pattern check
  evaluators/
    prompt-quality.ts   — built-in: score prompt via LLM judge
    code-lint.ts        — built-in: run linter, count errors
    test-pass-rate.ts   — built-in: run test suite, score = pass%
  mcp/
    server.ts           — MCP stdio server (tool definitions + handlers)
    schema.ts           — MCP tool JSON schemas
  cli/
    index.ts            — standalone CLI entry point
  types.ts              — shared type definitions
```

## 4. Evaluation Framework

### How users define evaluators

**Option A: Shell command** (simplest, most flexible)
```bash
# evaluator.sh — receives candidate on stdin, prints JSON to stdout
#!/bin/bash
candidate=$(cat)
# run your tests/checks against the candidate
result=$(echo "$candidate" | my-test-harness)
echo '{"score": 0.85, "diagnostics": {"errors": 2, "warnings": 5}}'
```

**Option B: Script path** (TypeScript/Python/any)
```typescript
// evaluator.ts — export a function
export async function evaluate(candidate: string): Promise<{score: number; diagnostics?: any}> {
  const result = await runTests(candidate);
  return { score: result.passRate, diagnostics: { failed: result.failures } };
}
```

**Option C: HTTP endpoint**
```
POST /evaluate
Body: {"candidate": "..."}
Response: {"score": 0.85, "diagnostics": {...}}
```

### Built-in evaluators (v0: just prompt-quality)

**prompt-quality**: Uses a second LLM call as judge. Scores on clarity, specificity, completeness, lack of ambiguity. Cheap but noisy — useful for bootstrapping, not production.

## 5. Optimization Loop

```
1. Initialize:
   - Load seed candidate (or generate from objective)
   - Run evaluator on seed → baseline score
   - Initialize budget tracker

2. Loop (while budget remains):
   a. PROPOSE: Send to proposer LLM:
      - Current best candidate
      - Score history (last N iterations)
      - ASI from reflector (what went wrong, what to try)
      - Constraints + banned patterns
      → Returns: new candidate + reasoning

   b. VALIDATE: Check constraints
      - Banned pattern check (regex)
      - Regression test runner
      - If fails → log, skip to next iteration

   c. EVALUATE: Run evaluator on new candidate
      → Returns: score + diagnostics

   d. REFLECT: Send to reflector LLM:
      - Previous best vs new candidate (diff)
      - Score delta
      - Evaluator diagnostics
      → Returns: ASI notes (what improved, what degraded, what to try next)

   e. UPDATE STATE:
      - If new score > best score → update best
      - Record candidate in history
      - Check early stop conditions
      - Update budget

3. Return OptimizeResult with best candidate + full trace
```

### Proposer prompt (core of the system)

```
You are optimizing a text artifact. Your goal: maximize the evaluator score.

## Current best (score: {score})
{candidate}

## History (last {N} iterations)
{history_summary}

## Evaluator feedback (ASI)
{reflector_notes}

## Constraints
{constraints}

Propose an improved version. Think step-by-step about what to change and why.
Return ONLY the complete new candidate text — no explanation wrapper.
```

### Reflector prompt

```
An artifact was evaluated. Analyze the results and provide guidance for the next iteration.

## Previous best (score: {prev_score})
{prev_candidate}

## New candidate (score: {new_score})
{new_candidate}

## Diff
{diff}

## Evaluator diagnostics
{diagnostics}

What improved? What degraded? What should the next iteration try?
Be specific and actionable. This will be fed to the proposer as guidance.
```

## 6. MCP Server Design

Single MCP server over stdio. Three tools:

### `optimize`
```json
{
  "name": "optimize",
  "description": "Optimize a text artifact through iterative propose-evaluate-reflect cycles",
  "inputSchema": {
    "type": "object",
    "properties": {
      "seed_candidate": {"type": "string", "description": "Starting artifact text"},
      "objective": {"type": "string", "description": "What to create/improve (if no seed)"},
      "evaluator_command": {"type": "string", "description": "Shell command that scores candidates (stdin→JSON stdout)"},
      "evaluator_builtin": {"type": "string", "enum": ["prompt-quality", "code-lint", "test-pass-rate"]},
      "max_iterations": {"type": "number", "default": 10},
      "max_time_seconds": {"type": "number", "default": 300},
      "target_score": {"type": "number"},
      "constraints": {"type": "array", "items": {"type": "string"}},
      "banned_patterns": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

### `optimize_status`
```json
{
  "name": "optimize_status",
  "description": "Check status of a running or completed optimization run",
  "inputSchema": {
    "type": "object",
    "properties": {
      "run_id": {"type": "string"}
    },
    "required": ["run_id"]
  }
}
```

### `optimize_stop`
```json
{
  "name": "optimize_stop",
  "description": "Early-stop a running optimization",
  "inputSchema": {
    "type": "object",
    "properties": {
      "run_id": {"type": "string"}
    },
    "required": ["run_id"]
  }
}
```

### Claude Code integration

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "optimize-anything": {
      "command": "bun",
      "args": ["run", "/path/to/optimize-anything/src/mcp/server.ts"]
    }
  }
}
```

Then in Claude Code: "Use the optimize tool to improve this prompt..."

### OpenClaw integration

Add to OpenClaw MCP config or use mcporter:
```bash
mcporter add optimize-anything --command "bun run /path/to/optimize-anything/src/mcp/server.ts"
```

## 7. OpenClaw Skill Adapter

```
skills/optimize-anything/
  SKILL.md              — OpenClaw skill instructions
  package.json          — metadata
```

### SKILL.md structure

```markdown
---
name: optimize-anything
description: Optimize any text artifact through iterative LLM-driven search
---

# optimize-anything

## When to use
- Improving prompts, system messages, SKILL.md files
- Tuning configs, templates, tool policies
- Any text artifact with a measurable quality signal

## Usage

### Via MCP (preferred)
The optimize-anything MCP server must be running. Use mcporter:
\`mcporter call optimize-anything.optimize --seed_candidate "..." --evaluator_command "..."\`

### Via CLI
\`bun run ~/projects/optimize-anything/src/cli/index.ts optimize --seed ./prompt.txt --eval ./eval.sh --max-iter 10\`

## Evaluator requirement
You MUST provide an evaluator. Without one, the optimizer will hallucinate improvements.
```

## 8. Built-in Evaluator Recipes

### v0: prompt-quality (LLM judge)
- Sends candidate prompt to a cheap model with a rubric
- Scores 0-1 on: clarity, specificity, completeness, safety
- Good for bootstrapping; not for production optimization

### v1+: test-pass-rate
- Runs a test suite against the artifact
- Score = tests passed / total tests
- Best for code and config optimization

### v1+: code-lint
- Runs linter (eslint, biome, etc.) on candidate
- Score = 1 - (errors / max_errors)
- Combine with test-pass-rate for code optimization

### v1+: agent-task-completion
- Runs an agent with the candidate (as system prompt / skill)
- Measures task completion on a benchmark set
- Most expensive but most realistic

## 9. ASI (Actionable Side Information)

ASI is the key mechanism that makes this work better than blind search.

**Flow:**
1. Evaluator returns `diagnostics` alongside score
2. Reflector LLM reads diagnostics + diff + scores
3. Reflector produces structured ASI notes
4. ASI is injected into the next proposer prompt

**What makes good ASI:**
- Specific ("test_auth_flow failed: expected 200, got 401" not "some tests failed")
- Actionable ("the prompt lacks explicit output format instructions")
- Cumulative (include patterns across iterations, not just last one)

**ASI budget:** Keep ASI under 500 tokens. Truncate old ASI, keep most recent + recurring themes.

## 10. Guardrails & Safety

| Guardrail | Implementation | Default |
|-----------|---------------|---------|
| Max iterations | Counter in budget tracker | 10 |
| Max tokens | Sum proposer + reflector tokens | 100k |
| Max wall time | setTimeout on run | 5 min |
| Regression tests | Run before accepting candidate | none |
| Banned patterns | Regex check on candidate | none |
| Constraints | Included in proposer prompt | none |
| Score floor | Reject candidates below threshold | none |
| Diff size limit | Reject candidates that change >X% | none (v1) |

**Hard rule:** If a candidate fails any regression test, it is discarded — never replaces the current best.

## 11. MVP Scope (v0)

### In v0 (smallest end-to-end value chain)
- [x] Core optimizer loop (propose → evaluate → reflect)
- [x] Shell command evaluator
- [x] MCP server with `optimize` tool (stdio)
- [x] CLI entry point
- [x] Budget tracking (iterations + time)
- [x] Run history + best candidate tracking
- [x] ASI flow (evaluator diagnostics → reflector → proposer)
- [x] Constraints (natural language, in proposer prompt)
- [x] Banned patterns (regex)
- [x] Single built-in evaluator: prompt-quality (LLM judge)

### v1 (after v0 works end-to-end)
- [ ] Regression test runner
- [ ] `optimize_status` and `optimize_stop` MCP tools
- [ ] HTTP endpoint evaluator
- [ ] Script path evaluator (import and call)
- [ ] Built-in evaluators: test-pass-rate, code-lint
- [ ] Multi-objective optimization (Pareto front)
- [ ] Persistent run storage (SQLite)
- [ ] OpenClaw SKILL.md packaging + clawhub publish

### v2 (if v1 proves useful)
- [ ] Generalization mode (optimize across multiple eval tasks)
- [ ] Population-based search (multiple candidates per iteration)
- [ ] Agent-task-completion evaluator
- [ ] Web UI for run visualization
- [ ] Diff size guardrail

## 12. File/Folder Structure

```
optimize-anything/
├── PLAN.md                    ← this file
├── README.md
├── package.json
├── tsconfig.json
├── bunfig.toml
├── src/
│   ├── core/
│   │   ├── optimizer.ts       ← main loop
│   │   ├── proposer.ts        ← LLM candidate generation
│   │   ├── evaluator.ts       ← evaluator runner dispatch
│   │   ├── reflector.ts       ← LLM reflection → ASI
│   │   ├── budget.ts          ← budget tracking + early stop
│   │   ├── state.ts           ← RunState, history, best tracking
│   │   └── constraints.ts     ← banned patterns, regression tests
│   ├── evaluators/
│   │   └── prompt-quality.ts  ← built-in LLM judge evaluator
│   ├── mcp/
│   │   ├── server.ts          ← MCP stdio server entry
│   │   └── schema.ts          ← tool JSON schemas
│   ├── cli/
│   │   └── index.ts           ← CLI entry point
│   └── types.ts               ← shared interfaces
├── tests/
│   ├── optimizer.test.ts
│   ├── evaluator.test.ts
│   └── proposer.test.ts
├── examples/
│   ├── optimize-prompt.sh     ← end-to-end prompt optimization example
│   ├── optimize-config.sh     ← config tuning example
│   └── eval-prompt.sh         ← example evaluator script
└── skill/                     ← OpenClaw skill packaging
    ├── SKILL.md
    └── package.json
```

## 13. Example Usage Scenarios

### Scenario 1: Optimize a system prompt

```bash
# evaluator: score prompt quality via LLM judge
bun run src/cli/index.ts optimize \
  --seed ./my-system-prompt.txt \
  --evaluator-builtin prompt-quality \
  --max-iter 5

# Output: best candidate written to ./my-system-prompt.optimized.txt
```

### Scenario 2: Optimize a SKILL.md for task completion

```bash
# evaluator: run agent with skill, measure task success
cat > eval.sh << 'EOF'
#!/bin/bash
candidate=$(cat)
echo "$candidate" > /tmp/test-skill.md
# run agent with this skill on 5 test tasks
results=$(run-agent-benchmark --skill /tmp/test-skill.md --tasks ./benchmark.json)
echo "$results"  # must output {"score": 0.8, "diagnostics": {"passed": 4, "failed": 1}}
EOF
chmod +x eval.sh

bun run src/cli/index.ts optimize \
  --seed ./skills/my-skill/SKILL.md \
  --evaluator-command ./eval.sh \
  --max-iter 10 \
  --constraint "never remove safety warnings" \
  --constraint "keep the skill under 200 lines"
```

### Scenario 3: Via Claude Code MCP

In Claude Code:
> "I have a system prompt in `prompts/analyzer.txt` that's not performing well on edge cases. Use the optimize tool with the evaluator at `./test-analyzer.sh` to improve it. Stop if you hit 0.95 accuracy."

Claude Code calls:
```json
{
  "tool": "optimize",
  "arguments": {
    "seed_candidate": "<contents of prompts/analyzer.txt>",
    "evaluator_command": "./test-analyzer.sh",
    "target_score": 0.95,
    "max_iterations": 10
  }
}
```

### Scenario 4: Via OpenClaw

```
User: optimize my trading agent's system prompt, use the backtest as evaluator
Agent: *reads prompt, writes eval.sh that runs backtest, calls optimize MCP tool*
Agent: Done — improved from 0.62 to 0.81 over 7 iterations. Here's the diff...
```

---

## Implementation Order

1. **`types.ts`** — nail down interfaces first
2. **`evaluator.ts`** — shell command evaluator (most important piece)
3. **`proposer.ts`** + **`reflector.ts`** — LLM calls
4. **`state.ts`** + **`budget.ts`** — run management
5. **`optimizer.ts`** — wire the loop together
6. **`cli/index.ts`** — CLI entry point for manual testing
7. **`mcp/server.ts`** — MCP wrapper
8. **`prompt-quality.ts`** — built-in evaluator
9. **Test end-to-end** with a real prompt optimization
10. **Ship v0**
