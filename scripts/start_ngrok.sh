#!/usr/bin/env bash
# Starts the Kalakriti FastAPI app bound to 0.0.0.0 (required for ngrok to reach it) and then
# opens an ngrok tunnel to it, printing the public URL ngrok generated. Never hardcode that URL -
# ngrok's free tier picks a new random one every time this script runs.
#
#   bash scripts/start_ngrok.sh
#
# Env vars (all optional):
#   PORT=8000            local port uvicorn binds to / ngrok tunnels to
#   PYTHON=.venv/bin/python   interpreter to run uvicorn with
#   NGROK_AUTHTOKEN=...  if set (e.g. loaded from .env), applied to ngrok before starting
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok is not installed or not on PATH. Install it from https://ngrok.com/download and re-run this script." >&2
  exit 1
fi

# Pick up NGROK_AUTHTOKEN from .env without printing it, and without requiring the caller to
# export it manually first.
if [ -z "${NGROK_AUTHTOKEN:-}" ] && [ -f "$ROOT/.env" ]; then
  NGROK_AUTHTOKEN="$(grep -E '^NGROK_AUTHTOKEN=' "$ROOT/.env" | tail -n1 | cut -d= -f2- || true)"
fi
if [ -n "${NGROK_AUTHTOKEN:-}" ]; then
  ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null
fi

UVICORN_PID=""
NGROK_PID=""
cleanup() {
  [ -n "$NGROK_PID" ] && kill "$NGROK_PID" 2>/dev/null || true
  [ -n "$UVICORN_PID" ] && kill "$UVICORN_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting the Kalakriti API on 0.0.0.0:$PORT ..."
"$PYTHON" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" >/tmp/kalakriti-uvicorn.log 2>&1 &
UVICORN_PID=$!

for i in $(seq 1 20); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/health" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

echo "Starting ngrok tunnel to port $PORT ..."
ngrok http "$PORT" --log=stdout >/tmp/kalakriti-ngrok.log 2>&1 &
NGROK_PID=$!

PUBLIC_URL=""
for i in $(seq 1 20); do
  PUBLIC_URL="$("$PYTHON" scripts/_ngrok_tunnel_url.py 2>/dev/null || true)"
  [ -n "$PUBLIC_URL" ] && break
  sleep 0.5
done

if [ -z "$PUBLIC_URL" ]; then
  echo "Could not read the ngrok public URL from http://127.0.0.1:4040/api/tunnels - check /tmp/kalakriti-ngrok.log" >&2
  wait "$UVICORN_PID" "$NGROK_PID"
  exit 1
fi

echo ""
echo "=================================================================="
echo " Kalakriti is live at:"
echo ""
echo "   Local:  http://127.0.0.1:$PORT/"
echo "   Mobile/public (ngrok): $PUBLIC_URL/"
echo ""
echo " Open the mobile/public URL above on your phone's browser."
echo " Press Ctrl+C to stop both the API server and the ngrok tunnel."
echo "=================================================================="
echo ""

wait "$UVICORN_PID" "$NGROK_PID"
