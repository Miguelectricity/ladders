#!/usr/bin/env bash
# Re-runs the API's startup, so feeds added to backend/data/mock are picked up
# without stopping ./dev.sh. Works by touching a watched file: uvicorn --reload
# restarts the app, and ingestion happens in the lifespan handler.
set -euo pipefail

cd "$(dirname "$0")"

API=${API:-http://localhost:8000}
WATCHED=backend/api.py
FEEDS=backend/data/mock

# Ingestion runs inside the API process, so its logs go to the ./dev.sh terminal
# and never reach this one. Run the same load here first to show them. Worth
# doing before the restart, not after: a feed that isn't valid JSON is logged
# and skipped rather than fatal, so the only symptom over there is a quietly
# lower job count - and if every feed is bad, we find out without taking down a
# server that is currently working.
feed_check() {
    uv run --quiet python - <<'PY'
from collections import Counter
import logging
import sys

from backend.approval.approval import approve_jobs
from backend.ingestion.ingestion import FEED_DIR, FeedError, load_feeds, process_raw
from backend.logging_config import PACKAGE_LOGGER, configure_logging


class ErrorFlag(logging.Handler):
    """Notice feeds that load_feeds() skipped - it logs those and carries on."""

    seen = False

    def emit(self, record):
        ErrorFlag.seen = True


configure_logging()
logging.getLogger(PACKAGE_LOGGER).addHandler(ErrorFlag(level=logging.ERROR))

# Under the package logger: configure_logging() only attaches a handler there.
log = logging.getLogger(f"{PACKAGE_LOGGER}.reingest")
try:
    jobs, failures = process_raw(load_feeds())
except FeedError as e:
    log.error(f"{e} - the API would fail to start, so not restarting it")
    sys.exit(1)

log.info(f"{len(jobs)} jobs parsed from {FEED_DIR}, {len(failures)} records skipped")

# Same approval pass the app runs at startup - it logs every rejection with its
# reason, which is the other half of the gap between "parsed" and "serving".
approved, rejected = approve_jobs(jobs)
tally = ", ".join(f"{n} {reason.lower()}" for reason, n in
                  Counter(reason for _, reason in rejected).most_common())
log.info(f"{len(approved)} approved, {len(rejected)} rejected" + (f" ({tally})" if rejected else ""))

sys.exit(2 if failures or ErrorFlag.seen else 0)
PY
}

total() {
    local body
    body=$(curl -sf --max-time 2 "$API/api/jobs?page_size=1") || return 1
    printf '%s' "$body" | sed -n 's/.*"total":\([0-9][0-9]*\).*/\1/p'
}

if ! before=$(total); then
    echo "No API on $API - start ./dev.sh first." >&2
    exit 1
fi

echo "Serving $before jobs. Checking $FEEDS..."

if ! command -v uv > /dev/null; then
    echo "uv not found - skipping the feed check." >&2
    check=0
else
    check=0
    feed_check || check=$?
fi

if [ "$check" -eq 1 ]; then
    exit 1
fi

echo "Re-running startup..."
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
        [ "$check" -eq 0 ] || echo "Some records or feeds were skipped - see the log above." >&2
        exit 0
    fi
    sleep 0.5
done

echo "API did not come back up - check the ./dev.sh output." >&2
exit 1
