#!/usr/bin/env bash
# Re-runs the API's startup, so feeds added to backend/data/mock are picked up
# without stopping ./dev.sh. Works by touching a watched file: uvicorn --reload
# restarts the app, and ingestion happens in the lifespan handler.
set -euo pipefail

cd "$(dirname "$0")"

API=${API:-http://localhost:8000}
WATCHED=backend/api.py

total() {
    local body
    body=$(curl -sf --max-time 2 "$API/api/jobs?page_size=1") || return 1
    printf '%s' "$body" | sed -n 's/.*"total":\([0-9][0-9]*\).*/\1/p'
}

if ! before=$(total); then
    echo "No API on $API - start ./dev.sh first." >&2
    exit 1
fi

echo "Serving $before jobs. Re-running startup..."
touch "$WATCHED"

# The reloader needs a moment to notice, and the old process keeps answering
# until it does - so wait for the API to go down before waiting for it to
# come back, or we would just re-read the pre-reload count.
for _ in $(seq 1 20); do
    sleep 0.5
    total > /dev/null 2>&1 || break
done

for _ in $(seq 1 40); do
    if after=$(total); then
        echo "Startup complete. Serving $after jobs."
        exit 0
    fi
    sleep 0.5
done

echo "API did not come back up - check the ./dev.sh output." >&2
exit 1
