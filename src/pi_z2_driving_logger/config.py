"""Configuration dataclass with all defaults for pi-z2-driving-logger."""

from dataclasses import dataclass, field


GPS_DEVICE_PRIMARY = (
    "/dev/serial/by-id/"
    "usb-u-blox_AG_-_www.u-blox.com_u-blox_7_-_GPS_GNSS_Receiver-if00"
)
GPS_DEVICE_FALLBACK = "/dev/ttyACM0"
GPS_BAUD_RATE = 9600

LOG_DIR_DEFAULT = "/home/yuiseki/pi-z2-driving-logs"
SESSIONS_SUBDIR = "sessions"

# GPIO pin numbers (BCM)
GPIO_BTN_LEFT = 21
GPIO_BTN_CENTER = 16
GPIO_BTN_RIGHT = 20
GPIO_BUZZER = 26
GPIO_LEDS = [17, 18, 27, 22, 25, 12, 13, 19]

# Button timing (seconds)
CHORD_WINDOW_S = 0.300        # both buttons must be pressed within this window
CHORD_HOLD_S = 1.0            # hold duration to confirm chord
DOUBLE_CLICK_MIN_S = 0.100    # minimum interval between two clicks
DOUBLE_CLICK_MAX_S = 0.600    # maximum interval between two clicks

# GPX flush interval (seconds)
GPX_FLUSH_INTERVAL_S = 60

# Buzzer durations (seconds)
BUZZER_LONG_MS = 800
BUZZER_SHORT_MS = 100

# LED blink intervals (seconds)
LED_STATE_BLINK_INTERVAL_S = 1.0
LED_ERROR_BLINK_INTERVAL_S = 0.1
LED_FLOW_STEP_S = 0.05
LED_BOUNCE_STEP_S = 0.05


@dataclass
class Config:
    """Runtime configuration for pi-z2-driving-logger."""

    gps_device: str = GPS_DEVICE_PRIMARY
    gps_baud_rate: int = GPS_BAUD_RATE
    log_dir: str = LOG_DIR_DEFAULT
    initial_driver_state: str = "other"

    # GPIO
    gpio_btn_left: int = GPIO_BTN_LEFT
    gpio_btn_center: int = GPIO_BTN_CENTER
    gpio_btn_right: int = GPIO_BTN_RIGHT
    gpio_buzzer: int = GPIO_BUZZER
    gpio_leds: list = field(default_factory=lambda: list(GPIO_LEDS))

    # Button timing
    chord_window_s: float = CHORD_WINDOW_S
    chord_hold_s: float = CHORD_HOLD_S
    double_click_min_s: float = DOUBLE_CLICK_MIN_S
    double_click_max_s: float = DOUBLE_CLICK_MAX_S

    # Storage
    gpx_flush_interval_s: float = GPX_FLUSH_INTERVAL_S

    # Buzzer
    buzzer_long_ms: int = BUZZER_LONG_MS
    buzzer_short_ms: int = BUZZER_SHORT_MS

    # LED
    led_state_blink_interval_s: float = LED_STATE_BLINK_INTERVAL_S
    led_error_blink_interval_s: float = LED_ERROR_BLINK_INTERVAL_S
    led_flow_step_s: float = LED_FLOW_STEP_S
    led_bounce_step_s: float = LED_BOUNCE_STEP_S
