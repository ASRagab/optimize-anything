import type { EventCallback, OptimizationEvent } from "../types.js";

export class EventEmitter {
  private callbacks: EventCallback[] = [];

  on(callback: EventCallback): () => void {
    this.callbacks.push(callback);
    return () => {
      this.callbacks = this.callbacks.filter((cb) => cb !== callback);
    };
  }

  emit(event: OptimizationEvent): void {
    for (const cb of this.callbacks) {
      cb(event);
    }
  }
}

export function serializeEvents(events: OptimizationEvent[]): string {
  return events.map((event) => JSON.stringify(event)).join("\n");
}

export function deserializeEvents(jsonl: string): OptimizationEvent[] {
  if (!jsonl.trim()) {
    return [];
  }

  return jsonl
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as OptimizationEvent);
}
