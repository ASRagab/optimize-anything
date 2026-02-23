"""Generate evaluator scripts from seed artifact analysis."""
from __future__ import annotations
import textwrap


def generate_evaluator_script(
    *,
    seed: str,
    objective: str,
    evaluator_type: str = "command",
) -> str:
    """Generate an evaluator script for the given seed and objective.

    The generated script reads {"candidate": "..."} from stdin
    and outputs {"score": <float>, ...} to stdout.

    Args:
        seed: The seed artifact text.
        objective: What to optimize for.
        evaluator_type: "command" for bash script, "http" for Python HTTP server.

    Returns:
        The script content as a string.
    """
    if evaluator_type == "http":
        return _generate_http_evaluator(seed, objective)
    return _generate_command_evaluator(seed, objective)


def _generate_command_evaluator(seed: str, objective: str) -> str:
    """Generate a bash evaluator script."""
    seed_length = len(seed)
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # Auto-generated evaluator for: {objective}
        # Seed length: {seed_length} chars
        #
        # Input:  JSON on stdin: {{"candidate": "<text>"}}
        # Output: JSON on stdout: {{"score": <float>, ...}}
        #
        # Customize the scoring logic below to match your objective.

        set -euo pipefail

        # Read candidate from stdin
        input=$(cat)
        candidate=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin)['candidate'])")

        # --- Scoring logic ---
        # Replace this with your actual evaluation.
        # The score should be a float where higher is better.
        length=${{#candidate}}

        # Example: score based on length similarity to seed
        seed_length={seed_length}
        if [ "$length" -eq 0 ]; then
            score="0.0"
        else
            # Ratio of min/max length as a simple similarity metric
            if [ "$length" -gt "$seed_length" ]; then
                score=$(python3 -c "print(round($seed_length / $length, 4))")
            else
                score=$(python3 -c "print(round($length / $seed_length, 4))")
            fi
        fi

        echo '{{"score": '"$score"', "length": '"$length"', "objective": "{objective}"}}'
    """)


def _generate_http_evaluator(seed: str, objective: str) -> str:
    """Generate a Python HTTP evaluator server."""
    seed_length = len(seed)
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated HTTP evaluator for: {objective}

        Seed length: {seed_length} chars

        Run: python evaluator.py
        Endpoint: POST http://localhost:8000/evaluate
        Input:  {{"candidate": "<text>"}}
        Output: {{"score": <float>, ...}}
        \"\"\"
        import json
        from http.server import HTTPServer, BaseHTTPRequestHandler

        SEED_LENGTH = {seed_length}


        class EvaluatorHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body)
                candidate = data.get("candidate", "")

                # --- Scoring logic ---
                # Replace this with your actual evaluation.
                length = len(candidate)
                if length == 0:
                    score = 0.0
                elif length > SEED_LENGTH:
                    score = round(SEED_LENGTH / length, 4)
                else:
                    score = round(length / SEED_LENGTH, 4)

                result = json.dumps({{
                    "score": score,
                    "length": length,
                    "objective": "{objective}",
                }})

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
