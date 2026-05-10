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

### Left button — walking / field survey mode

| Gesture | Event | Buzzer |
|---|---|---|
| Single click | `walk_poi` | ピッ (short×1) |
| Long press (≥1s) | `walk_poi_important` | ピー (medium×1) |
| Double click | `walk_poi_double` | ピピッ (short×2) |

Left button events do not change `driver_state`. GPS position is recorded when fix is available.

## Buzzer Feedback

| Event | Pattern |
|---|---|
| Startup | short×2 |
| Shutdown | long + short |
| Switch to self | short, short, long（ピピピー） |
| Switch to other | short, short（ピピッ） |
| No GPS fix warning | short×3 |
| Duplicate state warning | short×3 |

## LED Feedback

- **Self state**: leftmost LED steady on
- **Other state**: rightmost LED steady on
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

## Traccar integration

This logger can optionally upload valid GPS fixes and button events to a [Traccar](https://www.traccar.org/) server using the OsmAnd protocol.

**Local files remain the source of truth.** Traccar upload is best-effort — the logger continues running even when the network or the server is unavailable.

### How it works

- When `TRACCAR_ENABLED=true`, a background thread flushes a local spool queue to Traccar at a fixed interval.
- GPS position payloads are enqueued every `TRACCAR_SEND_INTERVAL_SECONDS` when a valid fix is available.
- Button events (driver state changes, walk-POI) are enqueued immediately when a valid fix is available.
- If the network is down or the server is unreachable, payloads stay in `pending/` and are retried automatically.
- HTTP 4xx responses move the payload to `failed/` (payload likely malformed).
- On process restart, any `sending/` leftovers are recovered to `pending/`.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TRACCAR_ENABLED` | `false` | Set to `true` to enable upload |
| `TRACCAR_ENDPOINT` | `http://100.107.123.105:30055/` | Traccar OsmAnd endpoint URL |
| `TRACCAR_DEVICE_ID` | `pi-z2-wh` | Device identifier registered in Traccar |
| `TRACCAR_SEND_INTERVAL_SECONDS` | `10` | Position upload interval (seconds) |
| `TRACCAR_QUEUE_DIR` | `/home/yuiseki/pi-z2-driving-logs/traccar-queue` | Spool queue directory |
| `TRACCAR_TIMEOUT_SECONDS` | `5` | HTTP request timeout |
| `TRACCAR_MAX_RETRY_PER_FLUSH` | `50` | Max items sent per flush cycle |

### CLI options

```bash
python3 -m pi_z2_driving_logger \
  --traccar-enabled \
  --traccar-endpoint http://100.107.123.105:30055/ \
  --traccar-device-id pi-z2-wh
```

### Queue directory structure

```
/home/yuiseki/pi-z2-driving-logs/traccar-queue/
  pending/   ← waiting to be sent
  sending/   ← in-flight (moved back to pending on restart)
  sent/      ← delivered successfully
  failed/    ← permanently rejected (corrupt or HTTP 4xx)
```

### Helper scripts

```bash
# Test connectivity
bash scripts/traccar_curl_test.sh

# Show queue counts
bash scripts/traccar_queue_status.sh

# Flush pending items once (for debugging)
TRACCAR_ENABLED=true bash scripts/traccar_flush_once.sh
```

### Operational notes

- The `sent/` directory grows indefinitely. Periodically clean it up:
  ```bash
  find /home/yuiseki/pi-z2-driving-logs/traccar-queue/sent -mtime +7 -delete
  ```
- The `failed/` directory holds payloads that were rejected. Inspect them and delete when no longer needed.
- If `pending/` accumulates many files (e.g., extended offline period), the next flush sends up to `TRACCAR_MAX_RETRY_PER_FLUSH` items per cycle. Increase the value or run `traccar_flush_once.sh` in a loop to drain faster.
