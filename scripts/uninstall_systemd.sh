#!/bin/bash
set -e
SERVICE=pi-z2-driving-logger.service

echo "Stopping $SERVICE..."
sudo systemctl stop "$SERVICE" || true

echo "Disabling $SERVICE..."
sudo systemctl disable "$SERVICE" || true

echo "Removing service file..."
sudo rm -f "/etc/systemd/system/$SERVICE"

sudo systemctl daemon-reload

echo "Done. $SERVICE has been removed."
