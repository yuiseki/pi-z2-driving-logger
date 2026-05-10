#!/usr/bin/env bash
set -euo pipefail

QUEUE_DIR="${TRACCAR_QUEUE_DIR:-/home/yuiseki/pi-z2-driving-logs/traccar-queue}"

echo "=== Traccar queue status: ${QUEUE_DIR} ==="
for sub in pending sending sent failed; do
    dir="${QUEUE_DIR}/${sub}"
    if [ -d "${dir}" ]; then
        count=$(find "${dir}" -maxdepth 1 -name "*.json" | wc -l)
        echo "  ${sub}/: ${count} files"
    else
        echo "  ${sub}/: (not found)"
    fi
done
