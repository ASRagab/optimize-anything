"""optimize-anything: Optimize any text artifact using gepa."""

from gepa.optimize_anything import optimize_anything

from optimize_anything.evaluators import command_evaluator, http_evaluator
from optimize_anything.intake import normalize_intake_spec
from optimize_anything.result_contract import build_optimize_summary

__all__ = [
    "optimize_anything",
    "command_evaluator",
    "http_evaluator",
    "normalize_intake_spec",
    "build_optimize_summary",
]
