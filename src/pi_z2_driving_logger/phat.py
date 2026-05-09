"""Maker pHAT hardware abstraction using gpiozero (with mock fallback)."""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_GPIOZERO_AVAILABLE = False

try:
    from gpiozero import Button as _Button  # type: ignore
    from gpiozero import LED as _LED  # type: ignore
    from gpiozero import Buzzer as _Buzzer  # type: ignore
    _GPIOZERO_AVAILABLE = True
    logger.info("gpiozero available; using real GPIO")
except ImportError:
    logger.warning("gpiozero not available; using mock GPIO objects")


# ---------------------------------------------------------------------------
# Mock classes for non-Pi environments
# ---------------------------------------------------------------------------

class _MockButton:
    """Mock button that is always not pressed."""

    def __init__(self, pin: int, pull_up: bool = True, bounce_time: Optional[float] = None):
        self.pin = pin
        self.is_pressed = False
        self.when_pressed: Optional[Callable] = None
        self.when_released: Optional[Callable] = None

    def close(self) -> None:
        pass


class _MockLED:
    def __init__(self, pin: int):
        self.pin = pin
        self.is_active = False

    def on(self) -> None:
        self.is_active = True

    def off(self) -> None:
        self.is_active = False

    def close(self) -> None:
        pass


class _MockBuzzer:
    def __init__(self, pin: int):
        self.pin = pin
        self.is_active = False

    def on(self) -> None:
        self.is_active = True

    def off(self) -> None:
        self.is_active = False

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# MakerPHAT
# ---------------------------------------------------------------------------

class MakerPHAT:
    """Maker pHAT hardware abstraction.

    Provides buttons, LEDs, and buzzer. Falls back to mock objects when
    gpiozero is not available (e.g., when running tests on a non-Pi host).
    """

    def __init__(
        self,
        gpio_btn_left: int = 21,
        gpio_btn_center: int = 16,
        gpio_btn_right: int = 20,
        gpio_buzzer: int = 26,
        gpio_leds: Optional[list] = None,
    ):
        if gpio_leds is None:
            gpio_leds = [17, 18, 27, 22, 25, 12, 13, 19]

        self._available = _GPIOZERO_AVAILABLE

        if self._available:
            Button = _Button  # type: ignore
            LED = _LED  # type: ignore
            Buzzer = _Buzzer  # type: ignore
        else:
            Button = _MockButton  # type: ignore
            LED = _MockLED  # type: ignore
            Buzzer = _MockBuzzer  # type: ignore

        self.btn_left = Button(gpio_btn_left, pull_up=True, bounce_time=0.05)
        self.btn_center = Button(gpio_btn_center, pull_up=True, bounce_time=0.05)
        self.btn_right = Button(gpio_btn_right, pull_up=True, bounce_time=0.05)
        self.buzzer = Buzzer(gpio_buzzer)
        self.leds = [LED(pin) for pin in gpio_leds]

        logger.info(
            "MakerPHAT initialized (gpio=%s, leds=%s)",
            "real" if self._available else "mock",
            gpio_leds,
        )

    def is_gpio_available(self) -> bool:
        return self._available

    def close(self) -> None:
        """Release all GPIO resources."""
        for obj in [self.btn_left, self.btn_center, self.btn_right, self.buzzer]:
            try:
                obj.close()
            except Exception:
                pass
        for led in self.leds:
            try:
                led.close()
            except Exception:
                pass
