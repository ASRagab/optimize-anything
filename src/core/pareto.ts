import type { CandidateRecord } from "../types.js";

export function dominates(a: Map<string, number>, b: Map<string, number>): boolean {
  const dimensions = new Set<string>([...a.keys(), ...b.keys()]);
  let strictlyBetter = false;

  for (const key of dimensions) {
    const aVal = a.get(key) ?? Number.NEGATIVE_INFINITY;
    const bVal = b.get(key) ?? Number.NEGATIVE_INFINITY;
    if (aVal < bVal) {
      return false;
    }
    if (aVal > bVal) {
      strictlyBetter = true;
    }
  }

  return strictlyBetter;
}

export function insertIntoFrontier(
  candidateIndex: number,
  candidates: CandidateRecord[],
  frontier: Set<number>,
): boolean {
  const next = candidates[candidateIndex];
  let dominatedByExisting = false;
  const pruned: number[] = [];

  for (const index of frontier) {
    const current = candidates[index];
    if (dominates(current.scores, next.scores)) {
      dominatedByExisting = true;
      break;
    }
    if (dominates(next.scores, current.scores)) {
      pruned.push(index);
    }
  }

  if (dominatedByExisting) {
    return false;
  }

  for (const index of pruned) {
    frontier.delete(index);
  }
  frontier.add(candidateIndex);
  return true;
}
