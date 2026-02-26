#!/usr/bin/env python3
"""Thin HTTP server wrapping a command evaluator.

Accepts POST / with {"candidate": "..."}, pipes to the command evaluator
via stdin, and returns the evaluator's JSON response.

GET / returns {"status": "ok"} for health/preflight checks.

Usage:
    python scripts/evaluator_http_server.py --evaluator-command bash evaluators/skill_clarity.sh
    python scripts/evaluator_http_server.py --port 9000 --evaluator-command bash evaluators/skill_clarity.sh
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler


class EvaluatorHandler(BaseHTTPRequestHandler):
    """HTTP handler that delegates scoring to a command evaluator."""

    evaluator_command: list[str] = []

    def do_GET(self) -> None:
        """Health check endpoint."""
        self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:
        """Score a candidate via the command evaluator."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json(400, {"score": 0.0, "error": "Empty request body"})
            return

        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"score": 0.0, "error": "Invalid JSON in request body"})
            return

        if "candidate" not in payload:
            self._send_json(400, {"score": 0.0, "error": "Missing 'candidate' field"})
            return

        # Forward to command evaluator
        stdin_data = json.dumps({"candidate": payload["candidate"]})
        try:
            proc = subprocess.run(
                self.evaluator_command,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            self._send_json(200, {"score": 0.0, "error": "Evaluator command timed out"})
            return
        except FileNotFoundError:
            self._send_json(200, {"score": 0.0, "error": f"Command not found: {self.evaluator_command[0]}"})
            return
        except OSError as e:
            self._send_json(200, {"score": 0.0, "error": f"Command failed: {e}"})
            return

        if proc.returncode != 0:
            self._send_json(200, {
                "score": 0.0,
                "error": f"Evaluator exited with code {proc.returncode}",
                "stderr": proc.stderr.strip()[:500],
            })
            return

        # Parse and forward the evaluator's JSON response
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self._send_json(200, {
                "score": 0.0,
                "error": "Evaluator output is not valid JSON",
                "stdout": proc.stdout.strip()[:500],
            })
            return

        self._send_json(200, result)

    def _send_json(self, status: int, data: dict) -> None:
        response = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response.encode())

    def log_message(self, format: str, *args) -> None:
        """Log to stderr with compact format."""
        print(f"[evaluator-http] {args[0]}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluator-http-server",
        description="HTTP server wrapping a command evaluator",
    )
    parser.add_argument("--port", type=int, default=8234, help="Port to listen on")
    # Must be last due to nargs="+"
    parser.add_argument(
        "--evaluator-command",
        nargs="+",
        required=True,
        help="Command evaluator to wrap (e.g., bash evaluators/skill_clarity.sh)",
    )
    args = parser.parse_args(argv)

    EvaluatorHandler.evaluator_command = args.evaluator_command

    server = HTTPServer(("localhost", args.port), EvaluatorHandler)
    print(f"Listening on http://localhost:{args.port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
