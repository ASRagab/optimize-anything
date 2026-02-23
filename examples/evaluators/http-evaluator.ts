/**
 * http-evaluator.ts — Example HTTP evaluator for optimize-anything.
 *
 * Scores candidates by word count proximity to a target.
 *
 * Start: bun run examples/evaluators/http-evaluator.ts
 * Test:  curl -X POST http://localhost:3456 \
 *          -H "Content-Type: application/json" \
 *          -d '{"candidate": "hello world"}'
 */

const TARGET_WORDS = 50;

const server = Bun.serve({
  port: 3456,
  async fetch(req) {
    if (req.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const body = (await req.json()) as { candidate?: string };
    const candidate = body.candidate ?? "";
    const words = candidate.split(/\s+/).filter(Boolean).length;
    const diff = Math.abs(words - TARGET_WORDS);
    const score = 1.0 / (1.0 + diff / 10.0);

    return Response.json({
      score,
      sideInfo: {
        wordCount: words,
        target: TARGET_WORDS,
        diff,
      },
    });
  },
});

console.error(`HTTP evaluator running on http://localhost:${server.port}`);
console.error(`Target: ${TARGET_WORDS} words`);
