# Jev judge A/B against the LLM judge (2026-10-17)

Objective for both judges: "Score the quality and clarity of this system prompt".
No intake file, so Jev scored one default dimension ("overall quality").
Jev model: `jev-latest` (answered as `jev-1.13.0`). LLM judge: `openai/gpt-5.6-luna`.
Each cell is the mean of 3 `score` runs, with the min-to-max spread in parentheses.

| Artifact | Jev | LLM judge |
|---|---|---|
| bad (nonsense prompt) | 0.054 (0.013) | 0.020 (0.000) |
| seed ("Be helpful.") | 0.161 (0.017) | 0.350 (0.150) |
| mid (short billing prompt) | 0.861 (0.023) | 0.880 (0.090) |
| strong (rules and success criteria) | 0.983 (0.000) | 0.870 (0.020) |

- Ranking agrees on bad < seed < {mid, strong}. The LLM judge scores mid and strong as a tie (0.88 vs 0.87). Jev ranks strong above mid.
- Jev spread was at most 0.023. The LLM judge spread was up to 0.150.
- Jev saturates near 0.98 for strong prompts, so a loop has little headroom above that.

## Optimize run

`optimize /tmp/jev-ab/seed.txt --jev-model jev-latest --budget 5` finished in 15.7 s.
The winner was re-scored 3 times by each judge:

| Judge | Seed | Winner |
|---|---|---|
| Jev | 0.160 | 0.979 |
| LLM judge | 0.433 | 0.913 |

The independent LLM judge also prefers the winner, so there is no sign the proposer gamed Jev in this run.

## Latency and cost

- Wall time per `score` call, including process start: Jev 0.4 s, LLM judge 3.3 to 4.1 s.
- Jev input per call: 380 to 580 tokens. At $0.042 per million input tokens that is about $0.00002 per call. Output tokens are free.
- LLM judge token cost was not measured.

## Limits

One seed, one objective, 4 artifacts, budget 5. This shows the integration works and ranks sensibly. It does not show Jev is a better judge across artifact types.

# Phase 2: three-dimension intake with rubric levels

Intake: `specificity` (0.4, 4 levels), `edge_case_handling` (0.35, 4 levels), `success_criteria` (0.25, 3 levels), and one hard constraint ("The text is written as instructions for an AI assistant"). Levels were written as generic prompt-quality rubrics, not tuned to the test artifacts.
Setups: Jev with levels, Jev with the generic scale (same dimensions, levels removed), and `openai/gpt-5.6-luna` on the same dimensions. Each cell is the mean of 3 `score` runs, with the spread in parentheses.

| Artifact | Jev + levels | Jev generic | LLM judge |
|---|---|---|---|
| bad | 0.039 (0.008) | 0.019 (0.004) | 0.011 (0.017) |
| seed | 0.025 (0.004) | 0.023 (0.005) | 0.056 (0.036) |
| mid | 0.844 (0.009) | 0.670 (0.012) | 0.703 (0.054) |
| strong | 0.994 (0.002) | 0.907 (0.003) | 0.807 (0.028) |

- Ranking: all three setups agree on {bad, seed} < mid < strong. Below 0.06 the order of bad and seed differs by setup, and the gaps are small.
- Spread: rubric levels gave the smallest spread (at most 0.009). The LLM judge's spread was up to 0.054.
- Mid-to-strong gap: 0.150 with levels, 0.237 generic, 0.104 LLM judge. Levels narrowed the gap Jev showed.
- Ceiling: **worse with levels.** The strong prompt scores 0.994 with levels, against 0.907 generic and 0.807 for the LLM judge. A prompt that meets the top level of each rubric maxes out, so a loop has no signal left above that point.
- The hard constraint never failed on any artifact, including the nonsense one, so the 0.0 gate was not exercised live. It is covered by unit tests only.

## Optimize run with the rubric intake

`optimize --jev-model jev-latest --intake-file intake.json --budget 5` finished in 17 s. The winner, re-scored 3 times:

| Judge | Seed | Winner |
|---|---|---|
| Jev + levels | 0.030 | 0.989 |
| LLM judge | 0.066 | 0.885 |

The independent LLM judge also prefers the winner, with every dimension at 0.87 or higher.

## What got worse

- The ceiling (above). Rubric levels make Jev easier to saturate, not harder.
- `bad` outscored `seed` under Jev with levels (0.039 vs 0.025) while the LLM judge had them the other way. Both are near the floor.

## Limits

One seed, one objective, rubrics written by the same author as the test. This does not show that levels help on other artifact types.
