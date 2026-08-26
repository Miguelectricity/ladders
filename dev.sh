#!/usr/bin/env bash
# Installs what's missing, then runs the API on :8000 and the frontend on :5173.
# Ctrl-C stops both. Vite proxies /api to uvicorn, so open http://localhost:5173.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv > /dev/null; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

if ! command -v npm > /dev/null; then
    echo "npm is required: https://nodejs.org" >&2
    exit 1
fi

echo "Syncing backend dependencies..."
uv sync --extra dev

if [ ! -d frontend/node_modules ]; then
    echo "Installing frontend dependencies..."
    (cd frontend && npm install)
fi

# Job control, so each server below becomes its own process group and cleanup
# can take down its whole tree - uvicorn's reloader and npm's vite child
# outlive a kill aimed at the parent alone.
set -m

cleanup() {
    trap - EXIT INT TERM
    for pid in "${api_pid:-}" "${web_pid:-}"; do
        [ -n "$pid" ] && kill -- -"$pid" 2> /dev/null || true
    done
}
trap cleanup EXIT INT TERM

uv run uvicorn backend.api:app --reload --port 8000 &
api_pid=$!

# --strictPort: fail loudly if 5173 is taken rather than drifting to another
# port, which would silently break the CORS origin the API allows.
(cd frontend && exec npm run dev -- --strictPort) &
web_pid=$!

echo
echo "  API       http://localhost:8000"
echo "  Frontend  http://localhost:5173"
echo

wait
