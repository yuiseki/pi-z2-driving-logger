#!/usr/bin/env bash
# Smoke-test: fetch teacher device positions via Traccar REST API.
# Requires .traccar.env (or exported TRACCAR_* env vars).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.traccar.env"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

: "${TRACCAR_BASE_URL:?Set TRACCAR_BASE_URL}"
: "${TRACCAR_USER:?Set TRACCAR_USER}"
: "${TRACCAR_PASSWORD:?Set TRACCAR_PASSWORD}"
: "${TRACCAR_TEACHER_DEVICE_UNIQUE_ID:?Set TRACCAR_TEACHER_DEVICE_UNIQUE_ID}"

echo "=== Traccar export smoke test ==="
echo "Base URL : $TRACCAR_BASE_URL"
echo "User     : $TRACCAR_USER"
echo "Device   : $TRACCAR_TEACHER_DEVICE_UNIQUE_ID"
echo ""

COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT

# Login
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -c "$COOKIE_JAR" \
    -X POST "$TRACCAR_BASE_URL/api/session" \
    -d "email=${TRACCAR_USER}&password=${TRACCAR_PASSWORD}")
echo "Login: HTTP $HTTP"
[[ "$HTTP" == "200" ]] || { echo "Login failed"; exit 1; }

# List devices
echo ""
echo "=== Devices ==="
curl -s -b "$COOKIE_JAR" "$TRACCAR_BASE_URL/api/devices" | python3 -m json.tool --no-ensure-ascii | grep -E '"id"|"name"|"uniqueId"' | head -20

# Latest position for teacher device
DEVICE_JSON=$(curl -s -b "$COOKIE_JAR" "$TRACCAR_BASE_URL/api/devices" | \
    python3 -c "import sys,json; devs=json.load(sys.stdin); uid='${TRACCAR_TEACHER_DEVICE_UNIQUE_ID}'; d=next((x for x in devs if x.get('uniqueId')==uid),None); print(d['id'] if d else '')")

echo ""
echo "=== Teacher device ID: $DEVICE_JSON ==="
if [[ -n "$DEVICE_JSON" ]]; then
    curl -s -b "$COOKIE_JAR" "$TRACCAR_BASE_URL/api/positions?deviceId=${DEVICE_JSON}" | \
        python3 -m json.tool --no-ensure-ascii | head -40
fi

# Logout
curl -s -b "$COOKIE_JAR" -X DELETE "$TRACCAR_BASE_URL/api/session" > /dev/null
echo ""
echo "Done."
