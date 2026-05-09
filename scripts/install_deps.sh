#!/bin/bash
set -e
sudo apt-get update
sudo apt-get install -y \
  python3-gpiozero \
  python3-lgpio \
  python3-serial \
  gpsd-clients \
  git \
  tmux
