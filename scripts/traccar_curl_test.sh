#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="${TRACCAR_ENDPOINT:-http://100.107.123.105:30055/}"
DEVICE_ID="${TRACCAR_DEVICE_ID:-pi-z2-wh}"
TS="$(date +%s)"

curl -v "${ENDPOINT}?id=${DEVICE_ID}&lat=35.681236&lon=139.767125&timestamp=${TS}&speed=0&bearing=0&altitude=0&accuracy=10&hdop=2.0&driver_state=test&event_type=manual_curl_test&source=pi_z2_driving_logger"
