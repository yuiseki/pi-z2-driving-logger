#!/usr/bin/env bash
# Run semantic post-processing on a pi-z2-driving-logger session.
#
# Usage:
#   ./scripts/export_semantic_trace.sh [SESSION_DIR] [OUTPUT_DIR]
#
# SESSION_DIR defaults to the latest session under ~/pi-z2-driving-logs/sessions/
# OUTPUT_DIR  defaults to SESSION_DIR/postprocess/
#
# Traccar credentials are read from .traccar.env (or TRACCAR_* env vars).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.traccar.env"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

: "${TRACCAR_BASE_URL:?Set TRACCAR_BASE_URL in .traccar.env}"
: "${TRACCAR_USER:?Set TRACCAR_USER in .traccar.env}"
: "${TRACCAR_PASSWORD:?Set TRACCAR_PASSWORD in .traccar.env}"
: "${TRACCAR_TEACHER_DEVICE_UNIQUE_ID:?Set TRACCAR_TEACHER_DEVICE_UNIQUE_ID in .traccar.env}"

SESSIONS_ROOT="${HOME}/pi-z2-driving-logs/sessions"

if [[ -n "${1:-}" ]]; then
    SESSION_DIR="$1"
else
    SESSION_DIR=$(ls -dt "$SESSIONS_ROOT"/[0-9]* 2>/dev/null | head -1)
    [[ -n "$SESSION_DIR" ]] || { echo "No sessions found under $SESSIONS_ROOT"; exit 1; }
fi

SESSION_ID=$(basename "$SESSION_DIR")
OUTPUT_DIR="${2:-${SESSION_DIR}/postprocess}"

echo "=== Semantic post-processing ==="
echo "Session  : $SESSION_ID"
echo "Input    : $SESSION_DIR"
echo "Output   : $OUTPUT_DIR"
echo "Teacher  : $TRACCAR_TEACHER_DEVICE_UNIQUE_ID"
echo ""

cd "$SCRIPT_DIR"
PYTHONPATH=src python3 -m pi_z2_driving_logger.postprocess \
    --session "$SESSION_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --traccar-base-url "$TRACCAR_BASE_URL" \
    --traccar-user "$TRACCAR_USER" \
    --traccar-password "$TRACCAR_PASSWORD" \
    --teacher-device "$TRACCAR_TEACHER_DEVICE_UNIQUE_ID"

echo ""
echo "=== Output files ==="
ls -lh "$OUTPUT_DIR/"
