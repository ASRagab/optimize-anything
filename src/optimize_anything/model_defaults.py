"""Project-owned defaults for LLM roles."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

DEFAULT_PROPOSER_MODEL: Final[str] = "openai/gpt-5.6-sol"
DEFAULT_EVALUATOR_MODEL: Final[str] = "openai/gpt-5.6-luna"


def resolve_proposer_model(
    explicit_model: str | None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve CLI, environment, then project default proposer precedence."""
    environment = os.environ if environ is None else environ
    return (
        explicit_model
        or environment.get("OPTIMIZE_ANYTHING_MODEL")
        or DEFAULT_PROPOSER_MODEL
    )
