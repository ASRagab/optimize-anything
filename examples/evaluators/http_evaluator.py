#!/usr/bin/env python3
"""Example HTTP evaluator that scores by candidate length."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        data = json.loads(body)
        candidate = data.get("candidate", "")
        score = min(len(candidate) / 100, 1.0)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"score": score, "length": len(candidate)}).encode())

if __name__ == "__main__":
    HTTPServer(("localhost", 8000), Handler).serve_forever()
