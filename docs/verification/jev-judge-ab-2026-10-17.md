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

# Phase 4: harder rubric top levels

Each dimension got one new level above its old top, written from a general standard (near-exhaustive coverage, with examples and named triggers) and not from the test artifacts. The old levels are unchanged. `specificity` and `edge_case_handling` now have 5 levels, `success_criteria` has 4. Jev with the v2 rubric was re-run against the same artifacts. Jev generic and LLM judge columns are the Phase 2 numbers (same inputs, not re-run for the table).

| Artifact | Jev + levels (v1) | Jev + levels (v2) | Jev generic | LLM judge |
|---|---|---|---|---|
| bad | 0.039 | 0.028 (0.002) | 0.019 | 0.011 |
| seed | 0.025 | 0.014 (0.003) | 0.023 | 0.056 |
| mid | 0.844 | 0.617 (0.001) | 0.670 | 0.703 |
| strong | 0.994 | 0.819 (0.005) | 0.907 | 0.807 |

- **Ceiling moved.** The strong prompt dropped from 0.994 to 0.819, below the generic scale (0.907) and close to the LLM judge (0.807).
- Mid-to-strong gap: 0.202 with v2, against 0.150 with v1.
- Ranking is unchanged: bad and seed below mid, mid below strong. Spread stayed at most 0.005.
- Per dimension, the strong prompt still scores 0.98 on `success_criteria` (its top level is only a bit harder than before) and 0.75 to 0.78 on the other two.

## Optimize run with the v2 rubric

`optimize --jev-model jev-latest --intake-file intake_v2.json --budget 5` finished in 28 s. Mean of 3 re-scores:

| Artifact | Jev (v2) | LLM judge |
|---|---|---|
| seed | 0.013 | 0.062 |
| winner (v2 run) | 0.750 | 0.896 |
| winner (v1 run) | 0.727 | 0.876 |
| strong (hand-written) | 0.819 | 0.831 |

## What got worse or needs care

- **The judges now disagree on the winners.** Jev v2 ranks the hand-written domain prompt (0.819) above both optimizer winners (0.750, 0.727). The LLM judge ranks both winners above it (0.896, 0.876 vs 0.831). Both winners are generic-assistant prompts, which the rubric dimensions do not reward as much as a domain-specific one.
- The v2 winner is 562 words, against 325 words for the v1 winner. The proposer appears to add length when the top levels ask for more coverage. This is one run and not a measured trend.
- Lower scores leave more room, but a single budget-5 run improved the seed to 0.750 and not past the hand-written prompt, so the loop did not close the gap in that budget.

## Limits

One seed, one objective, rubrics written by the same author as the test. The new top levels were not tuned to the artifacts, but they were written after seeing that the strong prompt saturated, so they are not independent of it.

# Phase 7: which judge predicts real task accuracy (budget 30)

**Question:** when a judge scores a system prompt, does the score predict how well the prompt works?

**Ground truth.** Domain: support-ticket triage with a fixed written policy (5 categories, 3 priority levels, JSON output). A candidate prompt is run as the system prompt on 30 hand-labeled tickets with `gpt-5.6-luna`, twice, and scored by exact match on category and priority ("accuracy" below, out of 60 runs). Neither judge sees the labels. Both judges get the same objective, which contains the policy, and the same three dimensions (`policy_fidelity`, `output_format`, `clarity_and_focus`). Three scorers: `Jev + levels` (my 5/4/4-level rubric), `Jev generic` (same dimensions, no levels), and `gpt-5.6-luna`.

**Optimization.** Seed: a one-sentence prompt (accuracy 0.00, because it never asks for JSON). Four runs, budget 30, same seed and proposer (`gpt-5.6-sol`): two with Jev + levels, two with the LLM judge. All 15 candidates the runs produced were scored on ground truth and by all three scorers (3 scoring runs each), together with 9 hand-written prompts: the seed, nonsense, format only, categories without priority rules, the full policy, the full policy with examples, the policy buried in filler, plausible but wrong priority rules, and the policy with a wrong threshold.

## Optimizer winners, real accuracy

| Run | Judge that chose it | Winner accuracy | Best candidate in that run |
|---|---|---|---|
| jev1 | Jev + levels | 0.867 | 0.867 (the winner) |
| jev2 | Jev + levels | 0.817 | 0.933 |
| llm1 | LLM judge | 0.867 | 0.933 |
| llm2 | LLM judge | 0.933 | 0.933 (tied) |

Mean winner accuracy: Jev 0.842, LLM judge 0.900. Copying the policy straight into the prompt scores 0.917, and with four examples 0.933. So the optimizer ended at the level of the policy text it was handed, not above it.

In-run scores were 0.97 to 0.99 for every winner under both judges. The judges saturated within the first one or two candidates, so most of the 30 calls had little signal.

## Does the score predict accuracy? (Spearman rank correlation with accuracy)

| Prompts | Jev + levels | Jev generic | LLM judge | word count |
|---|---|---|---|---|
| 9 hand-written (wide quality range) | 0.98 | 0.98 | 0.98 | 0.90 |
| All 24 | 0.24 | 0.48 | 0.62 | 0.26 |
| 15 optimizer candidates (all good, close together) | -0.45 | 0.26 | 0.31 | -0.43 |

Which candidate each scorer would pick among the 15 (best possible is 0.933; average candidate 0.868):

| Scorer | Pick | Accuracy of the pick |
|---|---|---|
| Jev + levels | `c_jev2_4` | 0.817 |
| Jev generic | `c_jev2_1` | 0.933 |
| LLM judge | `c_jev1_2` | 0.850 |

## What the data says

- **Both judges separate bad prompts from good ones.** Across the wide-quality set, all three rank the 9 hand-written prompts almost identically to real accuracy (0.98).
- **Neither judge picks the best of several good candidates.** On the 15 close candidates the correlations are weak (-0.45 to 0.31). With 60 runs per prompt, one ticket is 0.017, and the candidates differ by 0.82 to 0.93, so most of that spread is within sampling noise. This test cannot say which judge is better there.
- **Both judges miss confidently wrong rules.** The prompt with wrong priority rules has real accuracy 0.15, about the same as the format-only prompt (0.12). Judges score it 0.57 (Jev + levels), 0.43 (Jev generic), and 0.58 (LLM judge): level with or above "categories without priority rules" (0.63 accuracy, scores 0.56 to 0.68) and well above the format-only prompt (0.38 to 0.50). A clear, well-formatted prompt with wrong rules is mostly invisible to both.
- **My rubric levels did not help.** Jev + levels has the lowest overall correlation (0.24) and a negative one among the 15 candidates (-0.45), where it leans toward longer prompts (word count has -0.43 correlation with accuracy). Jev generic did better (0.48 overall) on the same dimensions. This contradicts the Phase 2 and Phase 4 impression that levels were an improvement; those runs had no ground truth.
- **On this evidence the LLM judge is slightly ahead** (0.62 overall correlation, winners 0.900 against 0.842), but with 4 winners and noisy ground truth the gap is not established.
- **Jev is far faster and cheaper per call**, and its repeated scores vary less (Phases 1 to 4).

## Limits

- 30 tickets and 2 repeats per prompt; accuracy has about a one-ticket (0.017) resolution and visible sampling noise.
- Tickets, labels, policy, and rubric levels were written by the same author. The target model is the same model as the LLM judge, which could favor it.
- One domain, one seed, 4 optimization runs. Do not read the winner means as a proven difference.
- The judge objective contained the policy. A judge with only a vague objective would do worse at detecting wrong rules.
- Scripts and data are in `/tmp/jev-gt`, not in the repo.
