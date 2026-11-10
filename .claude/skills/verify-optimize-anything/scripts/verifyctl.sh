#!/usr/bin/env bash
# Control script for verify-optimize-anything.
#   verifyctl.sh start          -> creates evidence dir, starts the stub, prints EVID=... and STUB_BASE=...
#   verifyctl.sh doctor <EVID>  -> read-only health check
#   verifyctl.sh stop <EVID>    -> kills only the stub PID recorded in <EVID>/stub/pid
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$SKILL_DIR/../../.." && pwd)"

start() {
  local evid="$REPO/smoke_outputs/verify-$(date -u +%Y%m%d-%H%M%S)-$$"
  mkdir -p "$evid/stub" "$evid/work"
  nohup "$REPO/.venv/bin/python" "$SKILL_DIR/scripts/fake_llm.py" --state-dir "$evid/stub" \
    > "$evid/stub/server.log" 2>&1 &
  for _ in $(seq 1 50); do
    [[ -s "$evid/stub/port" ]] && curl -fsS "http://127.0.0.1:$(cat "$evid/stub/port")/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  [[ -s "$evid/stub/port" ]] || { echo "stub failed to start; see $evid/stub/server.log" >&2; exit 1; }
  cp "$SKILL_DIR/scripts/marker_eval.sh" "$evid/work/marker_eval.sh"
  echo "http://127.0.0.1:$(cat "$evid/stub/port")/v1" > "$evid/stub/base"
  echo "EVID=$evid"
  echo "STUB_BASE=http://127.0.0.1:$(cat "$evid/stub/port")/v1"
}

doctor() {
  local evid="${1:?usage: verifyctl.sh doctor <EVID>}" ok=1
  cd "$REPO"
  echo "repo=$REPO git_head=$(git rev-parse --short HEAD) dirty=$(git status --porcelain | wc -l | tr -d ' ')"
  echo "package_version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
  if uv run optimize-anything --help >/dev/null 2>&1; then echo "cli=OK"; else echo "cli=FAIL"; ok=0; fi
  local pid port
  pid=$(cat "$evid/stub/pid" 2>/dev/null || true); port=$(cat "$evid/stub/port" 2>/dev/null || true)
  if [[ -n "$pid" && -n "$port" ]] && kill -0 "$pid" 2>/dev/null; then
    local health; health=$(curl -fsS "http://127.0.0.1:$port/health" 2>/dev/null || true)
    if [[ "$health" == *"\"pid\": $pid"* ]]; then echo "stub=OK port=$port pid=$pid (port owned by our pid)"
    else echo "stub=FAIL port $port not answering as pid $pid: $health"; ok=0; fi
  else echo "stub=DOWN (pid=$pid)"; ok=0; fi
  # Hosts only, never values. These env vars reroute real API calls (e.g. via a local proxy).
  for v in OPENAI_BASE_URL ANTHROPIC_BASE_URL GEMINI_API_BASE_URL; do
    local val="${!v:-}" host; host="${val#*://}"; echo "$v host=${host%%/*}"; done
  for v in OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY TYPESAFE_API_KEY; do
    if [[ -n "${!v:-}" ]]; then echo "$v=set"; else echo "$v=unset"; fi; done
  [[ $ok == 1 ]] && echo "doctor=PASS" || { echo "doctor=FAIL"; exit 1; }
}

stop() {
  local evid="${1:?usage: verifyctl.sh stop <EVID>}" pid
  pid=$(cat "$evid/stub/pid" 2>/dev/null || true)
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then kill "$pid"; echo "stopped stub pid=$pid"
  else echo "stub not running (pid=${pid:-none})"; fi
  rm -f "$evid/stub/port" "$evid/stub/pid"
  echo "evidence kept at $evid"
}

case "${1:-}" in
  start) start ;;
  doctor) shift; doctor "$@" ;;
  stop) shift; stop "$@" ;;
  *) echo "usage: verifyctl.sh start|doctor <EVID>|stop <EVID>" >&2; exit 2 ;;
esac
