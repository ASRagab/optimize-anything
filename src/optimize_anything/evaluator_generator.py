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
    model: str = "openai/gpt-4o-mini",
    dataset: bool = False,
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
    if resolved_evaluator_type == "judge":
        return _generate_judge_evaluator(
            seed,
            objective,
            template_family=template_family,
            rubric_summary=rubric_summary,
            quality_dimensions=quality_dimensions,
            model=model,
            dataset=dataset,
        )
    if resolved_evaluator_type == "composite":
        return _generate_composite_evaluator(
            seed,
            objective,
            template_family=template_family,
            rubric_summary=rubric_summary,
            quality_dimensions=quality_dimensions,
            model=model,
            dataset=dataset,
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


def _generate_judge_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
    model: str = "openai/gpt-4o-mini",
    dataset: bool = False,
) -> str:
    """Generate a Python LLM-judge evaluator script using litellm."""
    from optimize_anything.llm_judge import JUDGE_SYSTEM_PROMPT

    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json
        import os
        import sys
        from litellm import completion

        MODEL = {model!r}
        OBJECTIVE = {objective!r}
        TEMPLATE_FAMILY = {template_family!r}
        RUBRIC_SUMMARY = {rubric_summary!r}
        QUALITY_DIMENSIONS = {quality_dimensions!r}
        JUDGE_SYSTEM_PROMPT = {JUDGE_SYSTEM_PROMPT!r}

        def _build_prompt(candidate: str, example: object | None) -> str:
            dimensions_text = "\\n".join([f"- {{name}} (weight={{weight}})" for name, weight in QUALITY_DIMENSIONS])
            example_text = json.dumps(example, ensure_ascii=False, indent=2) if example is not None else "(none)"
            return f\"\"\"## Objective\n{{OBJECTIVE}}\n\n## Template Family\n{{TEMPLATE_FAMILY}}\n\n## Rubric Summary\n{{RUBRIC_SUMMARY}}\n\n## Quality Dimensions\n{{dimensions_text}}\n\n## Example Context (optional)\n{{example_text}}\n\n## Artifact to Evaluate\n```\n{{candidate}}\n```\n\nReturn JSON with keys: score, reasoning, and one key per quality dimension name. score must be in [0,1].\"\"\"

        def _api_key_available() -> bool:
            key_vars = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"]
            return any(os.environ.get(k) for k in key_vars)

        def _strip_code_fences(text: str) -> str:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
                cleaned = cleaned[first_newline + 1:]
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-len("```")].rstrip()
            return cleaned

        def main() -> int:
            try:
                data = json.load(sys.stdin)
            except json.JSONDecodeError:
                print(json.dumps({{"score": 0.0, "reasoning": "Input must be valid JSON."}}))
                return 0

            candidate = str(data.get("candidate", ""))
            example = data.get("example") if {dataset} else None

            if not _api_key_available():
                print(json.dumps({{
                    "score": 0.0,
                    "reasoning": "Missing API key. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY.",
                    "error": "missing_api_key"
                }}))
                return 0

            prompt = _build_prompt(candidate, example)
            try:
                response = completion(
                    model=MODEL,
                    messages=[
                        {{"role": "system", "content": JUDGE_SYSTEM_PROMPT}},
                        {{"role": "user", "content": prompt}},
                    ],
                    temperature=0.0,
                    timeout=60.0,
                    response_format={{"type": "json_object"}},
                )
                raw_content = response.choices[0].message.content
                cleaned_content = _strip_code_fences(raw_content) if raw_content else ""
                parsed = json.loads(cleaned_content) if cleaned_content else {{}}
            except Exception as exc:
                print(json.dumps({{"score": 0.0, "reasoning": f"LLM call failed: {{type(exc).__name__}}: {{exc}}"}}))
                return 0

            score = parsed.get("score", 0.0)
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(1.0, score))

            result = {{
                "score": score,
                "reasoning": str(parsed.get("reasoning", "No reasoning provided.")),
                "dimension_scores": {{name: parsed.get(name, 0.0) for name, _ in QUALITY_DIMENSIONS}},
            }}
            for name, _ in QUALITY_DIMENSIONS:
                value = parsed.get(name, result["dimension_scores"][name])
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = 0.0
                result[name] = max(0.0, min(1.0, value))

            print(json.dumps(result))
            return 0

        if __name__ == "__main__":
            raise SystemExit(main())
    """).lstrip()


def _generate_composite_evaluator(
    seed: str,
    objective: str,
    *,
    template_family: str,
    rubric_summary: str,
    quality_dimensions: list[tuple[str, float]],
    model: str = "openai/gpt-4o-mini",
    dataset: bool = False,
) -> str:
    """Generate composite evaluator with hard constraints + judge scoring."""
    judge_script = _generate_judge_evaluator(
        seed,
        objective,
        template_family=template_family,
        rubric_summary=rubric_summary,
        quality_dimensions=quality_dimensions,
        model=model,
        dataset=dataset,
    )
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import json
        import re
        import sys

        # Composite evaluator: hard constraints first, then LLM judge.
        def _constraint_non_empty(candidate: str) -> tuple[bool, str]:
            if candidate.strip():
                return True, ""
            return False, "candidate must not be empty"

        def _constraint_max_len(candidate: str, max_len: int = 12000) -> tuple[bool, str]:
            if len(candidate) <= max_len:
                return True, ""
            return False, f"candidate exceeds max_len={{max_len}}"

        def _constraint_no_placeholder(candidate: str) -> tuple[bool, str]:
            if re.search(r"TODO|TBD|\\[FILL\\]", candidate):
                return False, "candidate contains placeholder tokens"
            return True, ""

        JUDGE_SCRIPT = {judge_script!r}

        def _strip_code_fences(text: str) -> str:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
                cleaned = cleaned[first_newline + 1:]
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-len("```")].rstrip()
            return cleaned

        def _run_judge(payload: dict[str, object]) -> dict[str, object]:
            import subprocess
            proc = subprocess.run(
                [sys.executable, "-c", JUDGE_SCRIPT],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                return {{"score": 0.0, "reasoning": f"judge subprocess failed: {{proc.stderr.strip()}}"}}
            try:
                raw_output = proc.stdout.strip()
                cleaned_output = _strip_code_fences(raw_output) if raw_output else ""
                return json.loads(cleaned_output or "{{}}")
            except json.JSONDecodeError:
                return {{"score": 0.0, "reasoning": "judge returned invalid JSON"}}

        def main() -> int:
            try:
                data = json.load(sys.stdin)
            except json.JSONDecodeError:
                print(json.dumps({{"score": 0.0, "reasoning": "Input must be valid JSON"}}))
                return 0

            candidate = str(data.get("candidate", ""))
            checks = [_constraint_non_empty, _constraint_max_len, _constraint_no_placeholder]
            failures = []
            for check in checks:
                ok, reason = check(candidate)
                if not ok:
                    failures.append(reason)

            if failures:
                print(json.dumps({{
                    "score": 0.0,
                    "reasoning": "Hard constraints failed",
                    "hard_constraint_failures": failures,
                    "hard_constraints_satisfied": False,
                }}))
                return 0

            payload = {{"candidate": candidate}}
            if {dataset}:
                payload["example"] = data.get("example")
            result = _run_judge(payload)
            result["hard_constraints_satisfied"] = True
            print(json.dumps(result))
            return 0

        if __name__ == "__main__":
            raise SystemExit(main())
    """).lstrip()


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())
