"""Stop callback helpers for optimization runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def plateau_stop_callback(window: int = 10, threshold: float = 0.005) -> Callable[[Any], bool]:
    """Return a stop callback that triggers when best score plateaus.

    GEPA stop callbacks receive the current GEPA state and must return ``True``
    to stop optimization.
    """
    if window < 1:
        raise ValueError("window must be at least 1")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")

    history: list[float] = []

    def _stop(gepa_state: Any) -> bool:
        try:
            scores = getattr(gepa_state, "program_full_scores_val_set", None)
            if not scores:
                return False
            current_best = max(float(score) for score in scores)
        except Exception:
            return False

        history.append(current_best)
        if len(history) <= window:
            return False

        baseline = history[-(window + 1)]
        best_recent = max(history[-window:])
        improvement = best_recent - baseline
        return improvement <= threshold

    return _stop
