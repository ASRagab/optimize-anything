"""Generate evaluator scripts from seed artifact analysis."""
from __future__ import annotations
import json
import textwrap
from collections.abc import Mapping
from numbers import Real
from typing import Any

from optimize_anything.model_defaults import DEFAULT_EVALUATOR_MODEL


def generate_evaluator_script(
    *,
    seed: str,
    objective: str,
    evaluator_type: str | None = None,
    intake: Mapping[str, Any] | None = None,
    model: str | None = DEFAULT_EVALUATOR_MODEL,
    dataset: bool = False,
    backend: str = "api",
    api_base: str | None = None,
    api_fallback: bool = False,
    api_fallback_model: str | None = None,
    max_concurrency: int = 1,
) -> str:
    """Generate an evaluator script that reads input JSON and outputs score JSON."""
    normalized_intake = _normalize_intake_if_provided(intake)
    resolved_evaluator_type = _resolve_evaluator_type(
        evaluator_type=evaluator_type,
        normalized_intake=normalized_intake,
    )
    template_family = _select_template_family(normalized_intake)
    rubric_summary = _extract_rubric_summary(normalized_intake)
    quality_dimensions = _extract_quality_dimensions(normalized_intake)

    if resolved_evaluator_type == "http":
        return _generate_http_evaluator(
            seed,
            objective,
            template_family=template_family,
            rubric_summary=rubric_summary,
            quality_dimensions=quality_dimensions,
            dataset=dataset,
        )
    if resolved_evaluator_type in {"judge", "composite"} and backend == "api" and model is None:
        raise ValueError("API judge evaluators require a model")
    if resolved_evaluator_type in {"judge", "composite"}:
        return _generate_runtime_evaluator(
            objective,
            evaluator_type=resolved_evaluator_type,
            template_family=template_family,
            rubric_summary=rubric_summary,
            quality_dimensions=quality_dimensions,
            hard_constraints=list((normalized_intake or {}).get("hard_constraints", [])),
            model=model,
            dataset=dataset,
            backend=backend,
            api_base=api_base,
            api_fallback=api_fallback,
            api_fallback_model=api_fallback_model,
            max_concurrency=max_concurrency,
        )
    return _generate_command_evaluator(
        seed,
        objective,
        template_family=template_family,
        rubric_summary=rubric_summary,
        quality_dimensions=quality_dimensions,
        dataset=dataset,
    )


def _normalize_intake_if_provided(
    intake: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if intake is None:
        return None
    from optimize_anything.intake import normalize_intake_spec

    return normalize_intake_spec(intake)


def _resolve_evaluator_type(
    *,
    evaluator_type: str | None,
    normalized_intake: Mapping[str, Any] | None,
) -> str:
    if evaluator_type is not None:
        mode = evaluator_type.strip().lower()
        if mode not in {"judge", "command", "http", "composite"}:
            raise ValueError("evaluator_type must be 'judge', 'command', 'http', or 'composite'")
        return mode
    return "judge"


def _select_template_family(intake: Mapping[str, Any] | None) -> str:
    """Pick a script template family from normalized intake metadata."""
    artifact_class = str((intake or {}).get("artifact_class", "")).strip().lower()
    if artifact_class in {
        "instructional_content",
        "instruction_artifact",
        "executable_analytical",
    }:
        return artifact_class
    return "general_text"


def _extract_rubric_summary(intake: Mapping[str, Any] | None) -> str:
    """Build a compact rubric summary for evaluator diagnostics."""
    if not intake:
        return "No rubric summary provided."

    quality_dimension_summary = _format_quality_dimension_summary(
        intake.get("quality_dimensions")
    )
    if quality_dimension_summary is not None:
        return quality_dimension_summary

    for key in ("rubric_summary", "rubric_brief", "rubric"):
        value = intake.get(key)
        if value not in (None, ""):
            return _compact_text(value, max_length=240)

    fragments = _collect_rubric_fragments(
        intake,
        "criteria",
        "rubric_dimensions",
        "dimensions",
        "focus",
    )

    if fragments:
        joined = "; ".join(fragments)
        if len(joined) <= 240:
            return joined
        return f"{joined[:237]}..."

    return "No rubric summary provided."


def _format_quality_dimension_summary(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None

    fragments: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "")).strip()
        weight = item.get("weight")
        if not name or not isinstance(weight, (Real, str)):
            continue
        try:
            fragments.append(f"{name}:{float(weight):.2f}")
        except (TypeError, ValueError):
            continue

    if not fragments:
        return None
    return f"quality_dimensions={', '.join(fragments)}"


def _collect_rubric_fragments(
    intake: Mapping[str, Any],
    *keys: str,
) -> list[str]:
    fragments: list[str] = []
    for key in keys:
        value = intake.get(key)
        if value not in (None, ""):
            fragments.append(f"{key}={_compact_text(value, max_length=96)}")
    return fragments


def _default_quality_dimensions() -> list[tuple[str, float]]:
    """Return default quality dimensions, sourced from intake module constants."""
    from optimize_anything.intake import DEFAULT_QUALITY_DIMENSIONS
    return list(DEFAULT_QUALITY_DIMENSIONS)


def _extract_quality_dimensions(
    intake: Mapping[str, Any] | None,
) -> list[tuple[str, float]]:
    if not intake:
        return _default_quality_dimensions()

    raw_dimensions = intake.get("quality_dimensions")
    if not isinstance(raw_dimensions, list) or not raw_dimensions:
        return _default_quality_dimensions()

    dimensions: list[tuple[str, float]] = []
    for item in raw_dimensions:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        weight = item.get("weight")
        if not isinstance(weight, (Real, str)):
            continue
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        dimensions.append((name, weight))
    if dimensions:
        return dimensions
    return _default_quality_dimensions()


def _compact_text(value: Any, *, max_length: int) -> str:
    """Convert intake values to compact, ASCII-safe inline text."""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, ensure_ascii=True)
        except TypeError:
            text = str(value)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _dataset_extract_snippet() -> str:
    return textwrap.dedent("""\
        example = data.get("example")
        expected = ""
        if isinstance(example, dict):
            expected = str(example.get("expected", ""))
    """)


def _generate_command_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
    dataset: bool = False,
) -> str:
    """Generate a bash evaluator script."""
    seed_length = len(seed)
    objective_preview = objective.replace("\n", "\\n")
    rubric_preview = rubric_summary.replace("\n", "\\n")
    dataset_input = '{"candidate": "<text>", "example": {...}}' if dataset else '{"candidate": "<text>"}'
    dataset_extract = _dataset_extract_snippet() if dataset else 'example = None\nexpected = ""\n'
    dataset_diag = '        "example_used": example is not None,\n'
    dataset_compare = textwrap.dedent("""\
        expected_overlap = 0.0
        if expected:
            expected_overlap = 1.0 if expected.lower() in candidate_lower else 0.0
            score = round(min(1.0, score + 0.2 * expected_overlap), 4)
    """) if dataset else "expected_overlap = 0.0\n"
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # Auto-generated evaluator for: {objective_preview}
        # Seed length: {seed_length} chars
        # Template family: {template_family}
        # Rubric summary: {rubric_preview}

        set -euo pipefail

        input_file=$(mktemp)
        trap 'rm -f "$input_file"' EXIT
        cat > "$input_file"

        python3 - "$input_file" <<'PY'
        import json
        import sys

        SEED_LENGTH = {seed_length}
        OBJECTIVE = {objective!r}
        TEMPLATE_FAMILY = {template_family!r}
        RUBRIC_SUMMARY = {rubric_summary!r}
        QUALITY_DIMENSIONS = {quality_dimensions!r}

        try:
            with open(sys.argv[1], "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            print(json.dumps({{"score": 0.0, "error": "Input must be valid JSON"}}))
            raise SystemExit(0)

        candidate = str(data.get("candidate", ""))
        candidate_lower = candidate.lower()
{_indent(dataset_extract, 8)}
        length = len(candidate)
        if length == 0 or SEED_LENGTH == 0:
            length_similarity = 0.0
        else:
            length_similarity = min(length, SEED_LENGTH) / max(length, SEED_LENGTH)

        base_score = max(0.0, min(1.0, length_similarity))
        dimension_scores = {{}}
        weighted_score = 0.0
        for name, weight in QUALITY_DIMENSIONS:
            dim_score = round(base_score, 4)
            dimension_scores[str(name)] = dim_score
            weighted_score += float(weight) * dim_score

        score = round(weighted_score, 4)
{_indent(dataset_compare, 8)}
        result = {{
            "score": score,
            "objective": OBJECTIVE,
            "template_family": TEMPLATE_FAMILY,
            "rubric_summary": RUBRIC_SUMMARY,
            "quality_dimensions": QUALITY_DIMENSIONS,
            "dimension_scores": dimension_scores,
            "length": length,
            "length_similarity": round(length_similarity, 4),
            "dataset_mode": {dataset},
{dataset_diag}            "expected_overlap": round(expected_overlap, 4),
        }}

        print(json.dumps(result))
        PY
    """).lstrip()


def _generate_http_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
    dataset: bool = False,
) -> str:
    """Generate a Python HTTP evaluator server."""
    seed_length = len(seed)
    dataset_input = '{"candidate": "<text>", "example": {...}}' if dataset else '{"candidate": "<text>"}'
    dataset_extract = _dataset_extract_snippet() if dataset else 'example = None\n        expected = ""\n'
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated HTTP evaluator.

        Seed length: {seed_length} chars
        Endpoint: POST http://localhost:8000/evaluate
        Input:  {dataset_input}
        Output: {{\"score\": <float>, ...}}
        \"\"\"
        import json
        from http.server import HTTPServer, BaseHTTPRequestHandler

        SEED_LENGTH = {seed_length}
        OBJECTIVE = {objective!r}
        TEMPLATE_FAMILY = {template_family!r}
        RUBRIC_SUMMARY = {rubric_summary!r}
        QUALITY_DIMENSIONS = {quality_dimensions!r}
        EVALUATE_PATH = "/evaluate"


        class EvaluatorHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != EVALUATE_PATH:
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({{"error": f"Use POST {{EVALUATE_PATH}}"}}).encode())
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({{"score": 0.0, "error": "Input must be valid JSON"}}).encode())
                    return

                candidate = str(data.get("candidate", ""))
                candidate_lower = candidate.lower()
{_indent(dataset_extract, 16)}
                length = len(candidate)
                if length == 0 or SEED_LENGTH == 0:
                    score = 0.0
                else:
                    score = min(length, SEED_LENGTH) / max(length, SEED_LENGTH)

                if expected:
                    score = min(1.0, score + (0.2 if expected.lower() in candidate_lower else 0.0))

                payload = {{
                    "score": round(float(score), 4),
                    "objective": OBJECTIVE,
                    "template_family": TEMPLATE_FAMILY,
                    "rubric_summary": RUBRIC_SUMMARY,
                    "quality_dimensions": QUALITY_DIMENSIONS,
                    "dataset_mode": {dataset},
                    "example_used": example is not None,
                }}

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, format, *args):
                pass


        if __name__ == "__main__":
            server = HTTPServer(("localhost", 8000), EvaluatorHandler)
            print("Evaluator server running on http://localhost:8000/evaluate")
            server.serve_forever()
    """).lstrip()


def _generate_runtime_evaluator(
    objective: str,
    *,
    evaluator_type: str,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
    hard_constraints: list[str],
    model: str | None,
    dataset: bool,
    backend: str,
    api_base: str | None,
    api_fallback: bool,
    api_fallback_model: str | None,
    max_concurrency: int,
) -> str:
    """Generate a configuration wrapper for the installed evaluator runtime."""
    from optimize_anything.evaluator_runtime import RUNTIME_CONTRACT_VERSION

    config = {
        "min_runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        "evaluator_type": evaluator_type,
        "objective": objective,
        "template_family": template_family,
        "rubric_summary": rubric_summary,
        "quality_dimensions": quality_dimensions,
        "hard_constraints": hard_constraints,
        "model": model,
        "dataset": dataset,
        "backend": backend,
        "api_base": api_base,
        "api_fallback": api_fallback,
        "api_fallback_model": api_fallback_model,
        "max_concurrency": max_concurrency,
    }
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json
        import sys

        MODEL = {model!r}
        EVALUATOR_METADATA = {{"min_runtime_contract_version": {RUNTIME_CONTRACT_VERSION}}}
        CONFIG = {config!r}

        def main() -> int:
            try:
                from optimize_anything.evaluator_runtime import run_generated_evaluator
            except ImportError:
                for line in sys.stdin:
                    if line.strip():
                        print(json.dumps({{
                            "score": 0.0,
                            "error": "runtime_unavailable",
                            "reasoning": "Install or upgrade optimize-anything to run this evaluator.",
                        }}))
                return 0
            return run_generated_evaluator(CONFIG)

        if __name__ == "__main__":
            raise SystemExit(main())
    """).lstrip()


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())
