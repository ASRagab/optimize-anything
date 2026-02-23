import { describe, expect, it } from "bun:test";
import { EventEmitter, deserializeEvents, serializeEvents } from "../src/core/events.js";

describe("event system", () => {
  it("emits and collects events in order", () => {
    const emitter = new EventEmitter();
    const collected: string[] = [];
    emitter.on((e) => collected.push(e.type));
    emitter.emit({ type: "optimization_start", timestamp: 1 });
    emitter.emit({ type: "iteration_start", timestamp: 2 });
    expect(collected).toEqual(["optimization_start", "iteration_start"]);
  });

  it("serializes to JSONL and deserializes back", () => {
    const events = [
      { type: "optimization_start" as const, timestamp: 1 },
      { type: "evaluation_end" as const, timestamp: 2, data: { score: 0.9 } },
    ];
    const jsonl = serializeEvents(events);
    const parsed = deserializeEvents(jsonl);
    expect(parsed).toEqual(events);
  });
});
