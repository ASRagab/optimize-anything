"""Canonical optimize output contract shared by CLI and MCP."""

from __future__ import annotations

from typing import Any


def build_optimize_summary(result: Any) -> dict[str, Any]:
    """Normalize GEPA result objects into a stable output schema."""
    scores = _coerce_numeric_list(getattr(result, "val_aggregate_scores", None))
    best_idx = _resolve_best_idx(result, scores)
    initial_score = scores[0] if scores else None
    latest_score = scores[-1] if scores else None
    best_score = scores[best_idx] if best_idx is not None else None

    top_diagnostics = _extract_top_diagnostics(result, best_idx, best_score)
    plateau_detected, plateau_guidance = _compute_plateau_guidance(scores)

    return {
        "best_artifact": getattr(result, "best_candidate", None),
        "total_metric_calls": getattr(result, "total_metric_calls", None),
        "score_summary": {
            "initial": initial_score,
            "latest": latest_score,
            "best": best_score,
            "delta_latest_vs_initial": _delta(latest_score, initial_score),
            "delta_best_vs_initial": _delta(best_score, initial_score),
            "num_candidates": len(scores),
        },
        "top_diagnostics": top_diagnostics,
        "plateau_detected": plateau_detected,
        "plateau_guidance": plateau_guidance,
    }


def _coerce_numeric_list(raw: Any) -> list[float]:
    if not isinstance(raw, list):
        return []
    values: list[float] = []
    for value in raw:
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _resolve_best_idx(result: Any, scores: list[float]) -> int | None:
    if not scores:
        return None
    raw_idx = getattr(result, "best_idx", None)
    if isinstance(raw_idx, int) and 0 <= raw_idx < len(scores):
        return raw_idx
    return max(range(len(scores)), key=lambda idx: scores[idx])


def _extract_top_diagnostics(
    result: Any,
    best_idx: int | None,
    best_score: float | None,
) -> list[dict[str, float]]:
    raw = getattr(result, "val_aggregate_subscores", None)
    if (
        isinstance(raw, list)
        and best_idx is not None
        and best_idx < len(raw)
        and isinstance(raw[best_idx], dict)
    ):
        pairs: list[tuple[str, float]] = []
        for key, value in raw[best_idx].items():
            try:
                pairs.append((str(key), float(value)))
            except (TypeError, ValueError):
                continue
        pairs.sort(key=lambda item: item[1], reverse=True)
        if pairs:
            return [{"name": name, "value": value} for name, value in pairs[:3]]

    if best_score is None:
        return []
    return [{"name": "overall_score", "value": best_score}]


def _compute_plateau_guidance(scores: list[float]) -> tuple[bool, str]:
    if len(scores) < 3:
        return (
            False,
            "Run more optimization iterations before assessing plateau behavior.",
        )

    recent = scores[-5:] if len(scores) >= 5 else scores
    spread = max(recent) - min(recent)
    total_gain = scores[-1] - scores[0]
    plateau = spread < 0.01 and total_gain < 0.02
    if plateau:
        return (
            True,
            "Scores have flattened. Improve evaluator diagnostics, refine the objective, or increase budget.",
        )
    return (
        False,
        "No strong plateau detected. Continue iterating or tighten constraints to target specific gains.",
    )


def _delta(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return round(new - old, 6)

