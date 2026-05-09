#!/bin/bash
SESSIONS_DIR="/home/yuiseki/pi-z2-driving-logs/sessions"

if [ ! -d "$SESSIONS_DIR" ]; then
  echo "Sessions directory not found: $SESSIONS_DIR"
  exit 1
fi

LATEST_SESSION="$(ls -1t "$SESSIONS_DIR" | head -n1)"

if [ -z "$LATEST_SESSION" ]; then
  echo "No sessions found in $SESSIONS_DIR"
  exit 1
fi

EVENTS_FILE="$SESSIONS_DIR/$LATEST_SESSION/events.jsonl"

if [ ! -f "$EVENTS_FILE" ]; then
  echo "No events.jsonl found in $SESSIONS_DIR/$LATEST_SESSION"
  exit 1
fi

echo "Tailing: $EVENTS_FILE"
tail -f "$EVENTS_FILE"
