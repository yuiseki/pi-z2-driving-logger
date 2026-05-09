#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
sudo cp "$REPO_DIR/systemd/pi-z2-driving-logger.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pi-z2-driving-logger.service
echo "Installed. Run: sudo systemctl start pi-z2-driving-logger.service"
