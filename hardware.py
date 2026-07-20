"""GPIO: power button, channel button, backlight, audio amp enable.

Modern replacements for the original buttons.py:
  * gpiozero instead of RPi.GPIO (works on Bookworm / Pi 5 gpiochip)
  * pinctrl instead of the deprecated raspi-gpio (falls back if present)
  * runs fine off-Pi (everything becomes a no-op) so you can develop
    and test on a desktop.

Default wiring (BCM), same as the original build guide:
  GPIO 26  power button/switch (to GND)
  GPIO 20  channel button (to GND)          [new]
  GPIO 19  display backlight enable (PWM alt-function a5)
  GPIO 18  audio amp enable / shutdown pin
"""
import shutil
import subprocess

try:
    from gpiozero import Button, DigitalOutputDevice
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False


def _pin_tool():
    if shutil.which("pinctrl"):
        return "pinctrl"
    if shutil.which("raspi-gpio"):
        return "raspi-gpio"
    return None


class Hardware:
    def __init__(self, config, on_power_toggle=None, on_channel_press=None):
        self.cfg = config
        self.on_power_toggle = on_power_toggle
        self.on_channel_press = on_channel_press
        self.amp = None
        self._power_btn = None
        self._channel_btn = None
        self._tool = _pin_tool()

        if not GPIO_AVAILABLE:
            print("[hardware] gpiozero not available; GPIO disabled")
            return

        pins = config.get("pins", {})
        try:
            self.amp = DigitalOutputDevice(pins.get("amp_enable", 18),
                                           initial_value=True)
        except Exception as e:
            print("[hardware] amp pin unavailable: %s" % e)

        try:
            self._power_btn = Button(pins.get("power_button", 26),
                                     pull_up=True, bounce_time=0.05)
            self._power_btn.when_pressed = self._power_pressed
            if config.get("power_switch_mode", "toggle") == "switch":
                # Slide switch: released edge also toggles
                self._power_btn.when_released = self._power_pressed
        except Exception as e:
            print("[hardware] power button unavailable: %s" % e)

        try:
            self._channel_btn = Button(pins.get("channel_button", 20),
                                       pull_up=True, bounce_time=0.05)
            self._channel_btn.when_pressed = self._channel_pressed
        except Exception as e:
            print("[hardware] channel button unavailable: %s" % e)

    # -- callbacks ---------------------------------------------------------

    def _power_pressed(self):
        if self.on_power_toggle:
            self.on_power_toggle()

    def _channel_pressed(self):
        if self.on_channel_press:
            self.on_channel_press()

    # -- backlight -----------------------------------------------------------

    def _backlight_pin(self):
        return self.cfg.get("pins", {}).get("backlight", 19)

    def backlight(self, on):
        pin = self._backlight_pin()
        if not self._tool:
            return
        if self._tool == "pinctrl":
            args = ["pinctrl", "set", str(pin), "a5" if on else "ip"]
        else:
            args = ["raspi-gpio", "set", str(pin), "op a5" if on else "ip"]
            args = args[:3] + args[3].split()
        try:
            subprocess.run(args, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    # -- amp ----------------------------------------------------------------

    def amp_enable(self, on):
        if self.amp is None:
            return
        if on:
            self.amp.on()
        else:
            self.amp.off()

    def set_power(self, on):
        self.backlight(on)
        self.amp_enable(on)
