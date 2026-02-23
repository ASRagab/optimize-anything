import type { CandidateRecord, ExplanationSection, OptimizationEvent } from "../types.js";

type ExplainInput = {
  candidates: CandidateRecord[];
  frontier: number[];
  events: OptimizationEvent[];
  bestScore: number;
};

export function explainOptimization(input: ExplainInput): ExplanationSection {
  const { candidates, frontier, events, bestScore } = input;

  if (candidates.length === 0) {
    return {
      wins: [],
      regressions: [],
      dominantFactors: [],
      nextActions: ["No candidates were evaluated."],
      summary: "No optimization data available.",
    };
  }

  const wins: string[] = [];
  const regressions: string[] = [];
  const dominantFactors: string[] = [];
  const nextActions: string[] = [];

  // Analyze score trajectory
  const scores = candidates.map((c) => c.aggregateScore);
  const seedScore = scores[0];
  const improvement = bestScore - seedScore;

  if (improvement > 0) {
    wins.push(`Score improved from ${seedScore.toFixed(4)} to ${bestScore.toFixed(4)} (+${improvement.toFixed(4)})`);
  } else if (improvement === 0) {
    regressions.push("No improvement over seed candidate");
  }

  // Identify accepted vs rejected candidates
  const accepted = events.filter((e) => e.type === "candidate_accepted").length;
  const rejected = events.filter((e) => e.type === "candidate_rejected").length;
  const total = accepted + rejected;

  if (total > 0) {
    wins.push(`${accepted}/${total} proposed candidates improved the frontier`);
    if (rejected > accepted) {
      regressions.push(`${rejected}/${total} candidates were rejected (high rejection rate)`);
    }
  }

  // Analyze frontier composition
  if (frontier.length > 1) {
    wins.push(`Pareto frontier contains ${frontier.length} non-dominated candidates`);
  }

  // Analyze sideInfo for dominant factors
  const sideInfoKeys = new Map<string, number>();
  for (const candidate of candidates) {
    for (const si of candidate.sideInfo) {
      if (si.scores) {
        for (const key of Object.keys(si.scores)) {
          sideInfoKeys.set(key, (sideInfoKeys.get(key) ?? 0) + 1);
        }
      }
    }
  }
  for (const [key, count] of sideInfoKeys.entries()) {
    if (count >= candidates.length * 0.5) {
      dominantFactors.push(`"${key}" appeared in ${count}/${candidates.length} evaluations`);
    }
  }

  // Analyze frontier stagnation
  const frontierEvents = events.filter((e) => e.type === "frontier_updated");
  const lastFrontierUpdate = frontierEvents.at(-1);
  const totalIterations = events.filter((e) => e.type === "iteration_end").length;

  if (lastFrontierUpdate?.iterationIndex !== undefined && totalIterations > 0) {
    const stagnantIterations = totalIterations - lastFrontierUpdate.iterationIndex - 1;
    if (stagnantIterations > totalIterations * 0.5) {
      regressions.push(`Frontier stagnated for ${stagnantIterations} of ${totalIterations} iterations`);
      nextActions.push("Consider increasing budget or changing the evaluation criteria");
    }
  }

  // Suggest next actions
  if (improvement > 0 && totalIterations > 0) {
    const improvementRate = improvement / totalIterations;
    if (improvementRate > 0.01) {
      nextActions.push("Score is still improving — consider increasing maxMetricCalls for further gains");
    }
  }

  if (dominantFactors.length === 0 && candidates.some((c) => c.sideInfo.length > 0)) {
    nextActions.push("Evaluator provides sideInfo but no consistent sub-scores — consider adding structured scores for better guidance");
  }

  if (nextActions.length === 0) {
    nextActions.push("Run appears converged — review the best candidate qualitatively");
  }

  // Build summary
  const summaryParts: string[] = [];
  if (improvement > 0) {
    summaryParts.push(`Optimization improved score by ${improvement.toFixed(4)}`);
  } else {
    summaryParts.push("Optimization did not improve on the seed");
  }
  summaryParts.push(`${total} candidates evaluated across ${totalIterations} iterations`);
  if (frontier.length > 0) {
    summaryParts.push(`frontier size: ${frontier.length}`);
  }

  return {
    wins,
    regressions,
    dominantFactors,
    nextActions,
    summary: summaryParts.join(". ") + ".",
  };
}
