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
