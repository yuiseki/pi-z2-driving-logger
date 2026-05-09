# pi-z2-driving-logger

GPS driving logger for Raspberry Pi Zero 2 WH with Maker pHAT.

## Hardware

- **Board**: Raspberry Pi Zero 2 WH
- **GPS**: VFAN UG-353 / u-blox 7
  - Device: `/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_7_-_GPS_GNSS_Receiver-if00`
  - Fallback: `/dev/ttyACM0`
- **Maker pHAT** GPIO:
  - Left button: GPIO21
  - Center button: GPIO16
  - Right button: GPIO20
  - Buzzer: GPIO26 (active buzzer)
  - LED1-8: GPIO17, GPIO18, GPIO27, GPIO22, GPIO25, GPIO12, GPIO13, GPIO19

## Log Storage

- Default directory: `/home/yuiseki/pi-z2-driving-logs/`
- Per session: `/home/yuiseki/pi-z2-driving-logs/sessions/YYYYmmdd-HHMMSS/`
- Files per session:
  - `raw.nmea` — raw NMEA sentences
  - `events.jsonl` — driver state change events (JSON Lines)
  - `track.gpx` — full GPS track
  - `waypoints.gpx` — driver state change waypoints
  - `summary.json` — session summary
  - `state.json` — final state snapshot

## Button Controls

### Center + Right chord → switch to **self** (I am driving)

1. Press both Center (GPIO16) and Right (GPIO20) within 300ms
2. Hold both for 1 second
3. Release to confirm

### Right double-click → switch to **other** (someone else is driving)

1. Press Right button once
2. Press Right button again within 600ms (and at least 100ms after first)

### Left button

Reserved for future POI (point of interest) logging.

## Buzzer Feedback

| Event | Pattern |
|---|---|
| Startup | short×2 |
| Shutdown | long + short |
| Switch to self | long×1 |
| Switch to other | short×2 |
| No GPS fix warning | short×3 |
| Duplicate state warning | short×3 |

## LED Feedback

- **Self state**: leftmost LED slow blink
- **Other state**: rightmost LED slow blink
- **State change animation**: flow pattern pauses indicator, runs animation, resumes

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yuiseki/pi-z2-driving-logger.git
cd pi-z2-driving-logger
```

### 2. Install dependencies

```bash
bash scripts/install_deps.sh
```

### 3. Install as systemd service

```bash
bash scripts/install_systemd.sh
sudo systemctl start pi-z2-driving-logger.service
```

### 4. Tail latest session events

```bash
bash scripts/tail_latest.sh
```

## Development

### Run manually

```bash
bash scripts/run_logger.sh
# or with options:
python3 -m pi_z2_driving_logger --gps-device /dev/ttyACM0 --initial-driver-state other
```

### Run tests

```bash
python3 -m pytest tests/ -v
```

## Uninstall systemd service

```bash
bash scripts/uninstall_systemd.sh
```
