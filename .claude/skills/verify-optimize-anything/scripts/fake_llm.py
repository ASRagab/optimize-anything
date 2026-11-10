#!/usr/bin/env python3
"""Verification scaffolding: a local OpenAI-compatible chat endpoint.

Point optimize-anything at it with `--api-base http://127.0.0.1:<port>/v1`
and an `openai/<any>` model. It never forwards anything to a real provider.

Replies:
- Proposer prompts (text asks for ``` blocks): the current text from the first
  ``` block, with MARKER appended, inside a ``` block.
- Everything else (judge / analyze): a JSON object with exactly the keys the
  prompt's "Required JSON Output" section lists (the judge schema is strict).

Every request (path + body) is appended to <state-dir>/requests.jsonl.
Unknown paths get 404 and are logged too, so a route change is visible.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MARKER = "VERIFY-MARKER-7f3a"

DIMENSIONS = [
    {"name": "clarity", "weight": 0.6, "score": 0.7, "description": "stub dimension"},
    {"name": "concision", "weight": 0.4, "score": 0.6, "description": "stub dimension"},
]


def _prompt_text(body: dict) -> str:
    parts = []
    for msg in body.get("messages", []):
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(c.get("text", "") for c in content if isinstance(c, dict))
    return "\n".join(parts)


def _judge_reply(prompt: str) -> dict:
    # The judge validates replies against a strict schema (no extra keys), so
    # answer with exactly the keys the prompt's "Required JSON Output" lists.
    section = prompt.split("## Required JSON Output", 1)[-1].split("Example:", 1)[0]
    keys = re.findall(r'^- "([A-Za-z0-9_]+)"', section, re.M)
    if keys == ["dimensions"]:
        return {"dimensions": DIMENSIONS}
    # Dimensioned judges list dimensions earlier as "- <name> (weight=...)".
    keys += re.findall(r"^- ([A-Za-z0-9_]+) \(weight=", prompt, re.M)
    constraints = re.search(r"## Hard Constraints\n(.*?)(\n## |\Z)", prompt, re.S)
    if constraints and constraints.group(1).strip() not in ("", "(none)"):
        keys.append("hard_constraints_satisfied")
    reply: dict = {"score": 0.8, "reasoning": "stub judge reply"}
    for key in keys:
        if key == "hard_constraints_satisfied":
            reply[key] = True
        elif key not in reply:
            reply[key] = 0.8
    return reply


def _reply_for(prompt: str) -> str:
    if "```" in prompt and re.search(r"within ``` blocks|new instruction", prompt, re.I):
        match = re.search(r"```\n?(.*?)\n?```", prompt, re.S)
        current = match.group(1).strip() if match else "Improved artifact."
        if MARKER not in current:
            current = f"{current}\n{MARKER}"
        return f"```\n{current}\n```"
    return json.dumps(_judge_reply(prompt))


class Handler(BaseHTTPRequestHandler):
    state_dir: Path

    def _log(self, body: object, status: int) -> None:
        record = {"ts": time.time(), "method": self.command, "path": self.path, "status": status, "body": body}
        with (self.state_dir / "requests.jsonl").open("a") as fh:
            fh.write(json.dumps(record) + "\n")

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True, "pid": os.getpid(), "marker": MARKER})
            return
        self._log(None, 404)
        self._send(404, {"error": f"unknown path {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {"_raw": raw.decode(errors="replace")}
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._log(body, 404)
            self._send(404, {"error": f"unknown path {self.path}"})
            return
        content = _reply_for(_prompt_text(body))
        self._log(body, 200)
        self._send(
            200,
            {
                "id": "chatcmpl-verify",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "stub"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    Handler.state_dir = state_dir
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    (state_dir / "port").write_text(str(server.server_address[1]))
    (state_dir / "pid").write_text(str(os.getpid()))
    server.serve_forever()


if __name__ == "__main__":
    main()
