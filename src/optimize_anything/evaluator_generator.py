"""Generate evaluator scripts from seed artifact analysis."""
from __future__ import annotations
import json
import textwrap
from collections.abc import Mapping
from typing import Any


def generate_evaluator_script(
    *,
    seed: str,
    objective: str,
    evaluator_type: str | None = None,
    intake: Mapping[str, Any] | None = None,
) -> str:
    """Generate an evaluator script for the given seed and objective.

    The generated script reads {"candidate": "..."} from stdin
    and outputs {"score": <float>, ...} to stdout.

    Args:
        seed: The seed artifact text.
        objective: What to optimize for.
        evaluator_type: "command" for bash script, "http" for Python HTTP server.
        intake: Optional normalized intake metadata used to select template families.

    Returns:
        The script content as a string.
    """
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
        )
    return _generate_command_evaluator(
        seed,
        objective,
        template_family=template_family,
        rubric_summary=rubric_summary,
        quality_dimensions=quality_dimensions,
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
        if mode not in {"command", "http"}:
            raise ValueError("evaluator_type must be 'command' or 'http'")
        return mode
    if normalized_intake is not None:
        return str(normalized_intake["execution_mode"])
    return "command"


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

    quality_dimensions = intake.get("quality_dimensions")
    if isinstance(quality_dimensions, list) and quality_dimensions:
        fragments: list[str] = []
        for item in quality_dimensions:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name", "")).strip()
            weight = item.get("weight")
            if not name:
                continue
            try:
                fragments.append(f"{name}:{float(weight):.2f}")
            except (TypeError, ValueError):
                continue
        if fragments:
            return f"quality_dimensions={', '.join(fragments)}"

    for key in ("rubric_summary", "rubric_brief", "rubric"):
        value = intake.get(key)
        if value not in (None, ""):
            return _compact_text(value, max_length=240)

    fragments = []
    for key in ("criteria", "rubric_dimensions", "dimensions", "focus"):
        value = intake.get(key)
        if value not in (None, ""):
            fragments.append(f"{key}={_compact_text(value, max_length=96)}")

    if fragments:
        joined = "; ".join(fragments)
        if len(joined) <= 240:
            return joined
        return f"{joined[:237]}..."

    return "No rubric summary provided."


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
        try:
            weight = float(item.get("weight"))
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


def _generate_command_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
) -> str:
    """Generate a bash evaluator script."""
    seed_length = len(seed)
    objective_preview = objective.replace("\n", "\\n")
    rubric_preview = rubric_summary.replace("\n", "\\n")
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # Auto-generated evaluator for: {objective_preview}
        # Seed length: {seed_length} chars
        # Template family: {template_family}
        # Rubric summary: {rubric_preview}
        #
        # Input:  JSON on stdin: {{"candidate": "<text>"}}
        # Output: JSON on stdout: {{"score": <float>, ...}}
        #
        # Customize the scoring logic below to match your objective.

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
        length = len(candidate)

        if length == 0 or SEED_LENGTH == 0:
            length_similarity = 0.0
        else:
            length_similarity = min(length, SEED_LENGTH) / max(length, SEED_LENGTH)

        family_signal = 0.0
        family_diag = {{}}
        if TEMPLATE_FAMILY == "instructional_content":
            heading_hits = candidate.count("\\n#") + (1 if candidate.lstrip().startswith("#") else 0)
            list_hits = candidate.count("\\n- ") + candidate.count("\\n* ")
            ordered_hits = candidate.count("\\n1. ") + candidate.count("\\n2. ")
            family_signal = min(1.0, (heading_hits + list_hits + ordered_hits) / 10.0)
            family_diag = {{
                "instructional_structure": round(family_signal, 4),
                "heading_hits": heading_hits,
            }}
        elif TEMPLATE_FAMILY == "instruction_artifact":
            imperative_hits = sum(
                phrase in candidate_lower
                for phrase in ("use ", "run ", "click ", "set ", "add ", "remove ")
            )
            constraint_hits = sum(
                phrase in candidate_lower
                for phrase in ("must", "should", "required", "avoid", "do not")
            )
            family_signal = min(1.0, (imperative_hits + constraint_hits) / 6.0)
            family_diag = {{
                "instruction_precision": round(family_signal, 4),
                "imperative_hits": int(imperative_hits),
            }}
        elif TEMPLATE_FAMILY == "executable_analytical":
            code_hits = candidate.count("```") + sum(
                token in candidate for token in ("def ", "SELECT ", "FROM ", "{{", "}}", "();")
            )
            reasoning_hits = sum(
                phrase in candidate_lower
                for phrase in ("because", "therefore", "assume", "result", "tradeoff")
            )
            family_signal = min(1.0, (code_hits + reasoning_hits) / 8.0)
            family_diag = {{
                "analysis_executable_balance": round(family_signal, 4),
                "code_hits": int(code_hits),
            }}
        else:
            sentence_hits = candidate.count(".") + candidate.count("!") + candidate.count("?")
            paragraph_hits = candidate.count("\\n\\n")
            family_signal = min(1.0, (sentence_hits + paragraph_hits) / 20.0)
            family_diag = {{
                "general_coherence_signal": round(family_signal, 4),
                "sentence_hits": sentence_hits,
            }}

        def _dimension_signal(name: str) -> float:
            name_lower = name.lower()
            if "clarity" in name_lower or "readab" in name_lower or "structure" in name_lower:
                return family_signal
            if "correct" in name_lower or "accuracy" in name_lower or "factual" in name_lower:
                return length_similarity
            if "concise" in name_lower or "brev" in name_lower or "length" in name_lower:
                if length == 0 and SEED_LENGTH == 0:
                    return 1.0
                if length == 0 or SEED_LENGTH == 0:
                    return 0.0
                return max(0.0, 1.0 - (abs(length - SEED_LENGTH) / max(length, SEED_LENGTH)))
            return (length_similarity + family_signal) / 2

        dimension_scores = {{}}
        weighted_score = 0.0
        for name, weight in QUALITY_DIMENSIONS:
            dim_score = max(0.0, min(1.0, _dimension_signal(str(name))))
            dim_score = round(dim_score, 4)
            dimension_scores[str(name)] = dim_score
            weighted_score += float(weight) * dim_score

        score = round(weighted_score, 4)

        result = {{
            "score": score,
            "objective": OBJECTIVE,
            "template_family": TEMPLATE_FAMILY,
            "rubric_summary": RUBRIC_SUMMARY,
            "quality_dimensions": QUALITY_DIMENSIONS,
            "dimension_scores": dimension_scores,
            "length": length,
            "length_similarity": round(length_similarity, 4),
        }}
        result.update(family_diag)

        print(json.dumps(result))
        PY
    """)


def _generate_http_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
) -> str:
    """Generate a Python HTTP evaluator server."""
    seed_length = len(seed)
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated HTTP evaluator.

        Seed length: {seed_length} chars

        Run: python evaluator.py
        Endpoint: POST http://localhost:8000/evaluate
        Input:  {{"candidate": "<text>"}}
        Output: {{"score": <float>, ...}}
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
                    self.wfile.write(
                        json.dumps({{"error": f"Use POST {{EVALUATE_PATH}}"}}).encode()
                    )
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({{"score": 0.0, "error": "Input must be valid JSON"}}).encode()
                    )
                    return

                candidate = data.get("candidate", "")
                candidate_lower = str(candidate).lower()

                length = len(candidate)
                if length == 0 or SEED_LENGTH == 0:
                    length_similarity = 0.0
                else:
                    length_similarity = min(length, SEED_LENGTH) / max(length, SEED_LENGTH)

                family_signal = 0.0
                family_diag = {{}}
                if TEMPLATE_FAMILY == "instructional_content":
                    heading_hits = candidate.count("\\n#") + (1 if candidate.lstrip().startswith("#") else 0)
                    list_hits = candidate.count("\\n- ") + candidate.count("\\n* ")
                    ordered_hits = candidate.count("\\n1. ") + candidate.count("\\n2. ")
                    family_signal = min(1.0, (heading_hits + list_hits + ordered_hits) / 10.0)
                    family_diag = {{
                        "instructional_structure": round(family_signal, 4),
                        "heading_hits": heading_hits,
                    }}
                elif TEMPLATE_FAMILY == "instruction_artifact":
                    imperative_hits = sum(
                        phrase in candidate_lower
                        for phrase in ("use ", "run ", "click ", "set ", "add ", "remove ")
                    )
                    constraint_hits = sum(
                        phrase in candidate_lower
                        for phrase in ("must", "should", "required", "avoid", "do not")
                    )
                    family_signal = min(1.0, (imperative_hits + constraint_hits) / 6.0)
                    family_diag = {{
                        "instruction_precision": round(family_signal, 4),
                        "imperative_hits": int(imperative_hits),
                    }}
                elif TEMPLATE_FAMILY == "executable_analytical":
                    code_hits = candidate.count("```") + sum(
                        token in candidate for token in ("def ", "SELECT ", "FROM ", "{{", "}}", "();")
                    )
                    reasoning_hits = sum(
                        phrase in candidate_lower
                        for phrase in ("because", "therefore", "assume", "result", "tradeoff")
                    )
                    family_signal = min(1.0, (code_hits + reasoning_hits) / 8.0)
                    family_diag = {{
                        "analysis_executable_balance": round(family_signal, 4),
                        "code_hits": int(code_hits),
                    }}
                else:
                    sentence_hits = candidate.count(".") + candidate.count("!") + candidate.count("?")
                    paragraph_hits = candidate.count("\\n\\n")
                    family_signal = min(1.0, (sentence_hits + paragraph_hits) / 20.0)
                    family_diag = {{
                        "general_coherence_signal": round(family_signal, 4),
                        "sentence_hits": sentence_hits,
                    }}

                def _dimension_signal(name: str) -> float:
                    name_lower = name.lower()
                    if "clarity" in name_lower or "readab" in name_lower or "structure" in name_lower:
                        return family_signal
                    if "correct" in name_lower or "accuracy" in name_lower or "factual" in name_lower:
                        return length_similarity
                    if "concise" in name_lower or "brev" in name_lower or "length" in name_lower:
                        if length == 0 and SEED_LENGTH == 0:
                            return 1.0
                        if length == 0 or SEED_LENGTH == 0:
                            return 0.0
                        return max(0.0, 1.0 - (abs(length - SEED_LENGTH) / max(length, SEED_LENGTH)))
                    return (length_similarity + family_signal) / 2

                dimension_scores = {{}}
                weighted_score = 0.0
                for name, weight in QUALITY_DIMENSIONS:
                    dim_score = max(0.0, min(1.0, _dimension_signal(str(name))))
                    dim_score = round(dim_score, 4)
                    dimension_scores[str(name)] = dim_score
                    weighted_score += float(weight) * dim_score

                score = round(weighted_score, 4)

                payload = {{
                    "score": score,
                    "length": length,
                    "objective": OBJECTIVE,
                    "template_family": TEMPLATE_FAMILY,
                    "rubric_summary": RUBRIC_SUMMARY,
                    "quality_dimensions": QUALITY_DIMENSIONS,
                    "dimension_scores": dimension_scores,
                    "length_similarity": round(length_similarity, 4),
                }}
                payload.update(family_diag)
                result = json.dumps(payload)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(result.encode())

            def log_message(self, format, *args):
                pass  # Suppress default logging


        if __name__ == "__main__":
            server = HTTPServer(("localhost", 8000), EvaluatorHandler)
            print("Evaluator server running on http://localhost:8000/evaluate")
            server.serve_forever()
    """)
