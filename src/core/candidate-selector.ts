import type { CandidateRecord } from "../types.js";

function seededRandom(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x1_0000_0000;
  };
}

export function selectCurrentBest(candidates: CandidateRecord[]): number {
  if (candidates.length === 0) {
    return -1;
  }

  let bestIdx = 0;
  let bestScore = candidates[0].aggregateScore;
  for (let i = 1; i < candidates.length; i++) {
    if (candidates[i].aggregateScore > bestScore) {
      bestIdx = i;
      bestScore = candidates[i].aggregateScore;
    }
  }

  return bestIdx;
}

export function selectFromFrontier(
  _candidates: CandidateRecord[],
  frontier: Set<number>,
  seed = Date.now(),
): number {
  const indices = [...frontier];
  if (indices.length === 0) {
    return -1;
  }
  const random = seededRandom(seed);
  return indices[Math.floor(random() * indices.length)];
}

export function selectMinibatch<T>(dataset: T[], size: number, seed = Date.now()): T[] {
  if (size <= 0 || dataset.length === 0) {
    return [];
  }
  const random = seededRandom(seed);
  const shuffled = [...dataset];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, Math.min(size, shuffled.length));
}
