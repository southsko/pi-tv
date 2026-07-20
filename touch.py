"""Touchscreen gestures for the Waveshare 2.8" DPI capacitive panel.

The panel registers as a normal Linux input device (evdev), so no special
driver code is needed. Gestures (all configurable in config.json):

    tap                 play / pause
    swipe up/down       next / previous channel (with static effect)
    swipe left/right    seek -30s / +30s
    long press          power toggle (backlight + amp + pause)

Every gesture is remappable in config.json ("touch" -> "gestures") to any
of: pause, power, channel_up, channel_down, volume_up, volume_down,
next_episode, seek_fwd, seek_back, none.

Runs in its own thread; does nothing gracefully if there is no touch
device or python3-evdev is missing (e.g. desktop testing).
"""
import threading
import time

try:
    from evdev import InputDevice, ecodes, list_devices
    EVDEV = True
except ImportError:
    EVDEV = False


class TouchInput:
    def __init__(self, tv, config):
        self.tv = tv
        cfg = config.get("touch", {})
        self.enabled = cfg.get("enabled", True)
        self.rotate = int(cfg.get("rotate", 0)) % 360
        self.swipe_px = int(cfg.get("swipe_px", 80))
        self.long_press_s = float(cfg.get("long_press_s", 0.8))
        self.seek_step = int(cfg.get("seek_step", 30))
        self.gestures = {
            "tap": "pause",
            "long_press": "power",
            "up": "channel_up",
            "down": "channel_down",
            "left": "seek_back",
            "right": "seek_fwd",
        }
        self.gestures.update(cfg.get("gestures", {}))
        self.dev = None

    def _do(self, action):
        tv, vol_step = self.tv, 10
        {
            "pause": tv.toggle_pause,
            "power": tv.toggle_power,
            "channel_up": lambda: tv.change_channel(1),
            "channel_down": lambda: tv.change_channel(-1),
            "volume_up": lambda: tv.set_volume(tv.channels.volume + vol_step),
            "volume_down": lambda: tv.set_volume(tv.channels.volume - vol_step),
            "next_episode": tv.next_episode,
            "seek_fwd": lambda: tv.seek(self.seek_step),
            "seek_back": lambda: tv.seek(-self.seek_step),
            "none": lambda: None,
        }.get(action, lambda: None)()

    def start(self):
        if not self.enabled:
            return
        if not EVDEV:
            print("[touch] python3-evdev not installed; touch disabled")
            return
        t = threading.Thread(target=self._run, daemon=True, name="touch")
        t.start()

    # -- device discovery ---------------------------------------------------

    def _find_device(self):
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except OSError:
                continue
            caps = dev.capabilities()
            abs_codes = [c for c, _ in caps.get(ecodes.EV_ABS, [])]
            key_codes = caps.get(ecodes.EV_KEY, [])
            if (ecodes.ABS_MT_POSITION_X in abs_codes
                    or (ecodes.ABS_X in abs_codes
                        and ecodes.BTN_TOUCH in key_codes)):
                print("[touch] using %s (%s)" % (dev.path, dev.name))
                return dev
        return None

    # -- main loop ------------------------------------------------------------

    def _run(self):
        while True:
            self.dev = self._find_device()
            if self.dev is None:
                time.sleep(10)  # device may appear later
                continue
            try:
                self._read_loop()
            except OSError:
                print("[touch] device lost, rescanning")
                time.sleep(2)

    def _read_loop(self):
        x = y = 0
        down_x = down_y = 0
        down_t = None
        touching = False

        for event in self.dev.read_loop():
            if event.type == ecodes.EV_ABS:
                if event.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                    x = event.value
                elif event.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                    y = event.value
            elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                if event.value == 1 and not touching:
                    touching = True
                    down_x, down_y, down_t = x, y, time.time()
                elif event.value == 0 and touching:
                    touching = False
                    if down_t is not None:
                        self._gesture(x - down_x, y - down_y,
                                      time.time() - down_t)

    # -- gesture classification --------------------------------------------

    def _gesture(self, dx, dy, duration):
        # Undo panel rotation so swipes match what the viewer sees
        if self.rotate == 90:
            dx, dy = dy, -dx
        elif self.rotate == 180:
            dx, dy = -dx, -dy
        elif self.rotate == 270:
            dx, dy = -dy, dx

        if abs(dx) < self.swipe_px and abs(dy) < self.swipe_px:
            self._do(self.gestures["long_press"]
                     if duration >= self.long_press_s
                     else self.gestures["tap"])
        elif abs(dx) >= abs(dy):
            self._do(self.gestures["right" if dx > 0 else "left"])
        else:
            self._do(self.gestures["down" if dy > 0 else "up"])
