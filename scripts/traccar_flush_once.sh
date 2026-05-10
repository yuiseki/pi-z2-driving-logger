#!/usr/bin/env bash
# One-shot flush: send pending Traccar payloads via the Python module.
set -euo pipefail

PYTHONPATH="${PYTHONPATH:-/home/yuiseki/Workspaces/repos/_yuiseki/pi-z2-driving-logger/src}"
export PYTHONPATH

python3 - <<'EOF'
import os, sys
sys.path.insert(0, os.environ["PYTHONPATH"])
from pi_z2_driving_logger.traccar import TraccarConfig
from pi_z2_driving_logger.traccar_queue import TraccarQueue

cfg = TraccarConfig.from_env()
if not cfg.enabled:
    print("TRACCAR_ENABLED is not true; set it to flush manually.")
    sys.exit(1)

q = TraccarQueue(cfg.queue_dir)
q.recover_sending()
sent, requeued, failed = q.flush(
    endpoint=cfg.endpoint,
    device_id=cfg.device_id,
    max_count=cfg.max_retry_per_flush,
    timeout_s=cfg.timeout_s,
)
print(f"Flushed: sent={sent} requeued={requeued} failed={failed}")
EOF
