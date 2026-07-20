"""GPIO: power button, screen backlight, PWM audio gate.

Matches the Waveshare 2.8" DPI touch LCD build (the screen in the current
Simpsons TV build guide). The DPI bus eats nearly every GPIO; per the
pinout the only free ones are:

  GPIO 26  power button (to GND)          <- the classic TV knob
  GPIO 18  screen backlight (drive high = on, low = off)
  GPIO 19  PWM audio out to the amp (alt-function a5 = sound,
           input mode = silence)

There is NO spare pin for a channel button or amp-enable on this screen —
use touch or the web remote for channels. For other displays, the pins
(and an optional channel_button / amp_enable) are configurable in
config.json; set a pin to null to disable it.

Modernizations vs the original buttons.py: gpiozero instead of RPi.GPIO,
pinctrl instead of the deprecated raspi-gpio (auto-fallback), and
everything no-ops gracefully off-Pi so you can develop on a desktop.
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
        self.pins = config.get("pins", {})
        self.on_power_toggle = on_power_toggle
        self.on_channel_press = on_channel_press
        self.amp = None
        self._power_btn = None
        self._channel_btn = None
        self._tool = _pin_tool()

        if not GPIO_AVAILABLE:
            print("[hardware] gpiozero not available; GPIO disabled")
            return

        amp_pin = self.pins.get("amp_enable")
        if amp_pin:
            try:
                self.amp = DigitalOutputDevice(amp_pin, initial_value=True)
            except Exception as e:
                print("[hardware] amp pin unavailable: %s" % e)

        power_pin = self.pins.get("power_button", 26)
        if power_pin:
            try:
                self._power_btn = Button(power_pin, pull_up=True,
                                         bounce_time=0.05)
                self._power_btn.when_pressed = self._power_pressed
                if config.get("power_switch_mode", "toggle") == "switch":
                    self._power_btn.when_released = self._power_pressed
            except Exception as e:
                print("[hardware] power button unavailable: %s" % e)

        ch_pin = self.pins.get("channel_button")
        if ch_pin:
            try:
                self._channel_btn = Button(ch_pin, pull_up=True,
                                           bounce_time=0.05)
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

    # -- pin control (pinctrl / raspi-gpio) --------------------------------

    def _pinset(self, pin, *args):
        if not self._tool or pin is None:
            return
        try:
            subprocess.run([self._tool, "set", str(pin)] + list(args),
                           check=False, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def backlight(self, on):
        """Waveshare 2.8 DPI: GPIO 18 high = backlight on, low = off."""
        pin = self.pins.get("backlight", 18)
        self._pinset(pin, "op", "dh" if on else "dl")

    def audio(self, on):
        """GPIO 19 carries PWM audio when in alt-function; input = mute."""
        pin = self.pins.get("audio_pwm", 19)
        if pin is None:
            return
        self._pinset(pin, "a5" if on else "ip")

    def amp_enable(self, on):
        if self.amp is None:
            return
        if on:
            self.amp.on()
        else:
            self.amp.off()

    def set_power(self, on):
        self.backlight(on)
        self.audio(on)
        self.amp_enable(on)
