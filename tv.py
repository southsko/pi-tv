#!/usr/bin/env python3
"""Simpsons TV — modernized. Main service.

Replaces the original player.py + buttons.py pair with a single service:
  * mpv (JSON IPC) instead of the long-dead omxplayer
  * channels: each subfolder of videos/ is a channel
  * TV-static clip plays between channel changes
  * GPIO power + channel buttons (gpiozero)
  * web remote on port 8080 (play/pause/skip/channel/volume/upload)

Run directly for testing:  python3 tv.py
Installed as a systemd service by install.sh.
"""
import json
import os
import threading
import time

from channels import ChannelManager
from hardware import Hardware
from mpv_ipc import MPV, MPVError
from touch import TouchInput
from webui import create_app

BASE = os.path.dirname(os.path.realpath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")

DEFAULT_CONFIG = {
    "videos_dir": os.path.join(BASE, "videos"),
    "static_clip": os.path.join(BASE, "static.mp4"),
    "state_file": os.path.join(BASE, "state.json"),
    "web_port": 8080,
    "power_switch_mode": "toggle",
    "pins": {"power_button": 26, "channel_button": None,
             "backlight": 18, "audio_pwm": 19, "amp_enable": None},
    "mpv_args": ["--vo=gpu", "--gpu-context=drm", "--hwdec=auto-safe",
                 "--ao=alsa", "--panscan=1.0"]
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


class TV:
    def __init__(self, cfg):
        self.cfg = cfg
        self.channels = ChannelManager(cfg["videos_dir"], cfg["state_file"])
        self.power = True
        self.playing_static = False
        self.current_file = None
        self._lock = threading.Lock()

        self.mpv = MPV(extra_args=cfg.get("mpv_args", []),
                       event_handler=self._on_mpv_event)
        self.hw = Hardware(cfg,
                           on_power_toggle=self.toggle_power,
                           on_channel_press=lambda: self.change_channel(1))
        self.touch = TouchInput(self, cfg)

    # -- startup ------------------------------------------------------------

    def start(self):
        self.mpv.start()
        self.mpv.set("volume", self.channels.volume)
        for prop, val in (("osd-align-x", "center"), ("osd-align-y", "center")):
            try:
                self.mpv.set(prop, val)
            except MPVError:
                pass
        self.hw.set_power(True)
        self.touch.start()
        self.next_episode()

    def osd(self, text, duration_ms=1500):
        try:
            self.mpv.command("show-text", text, duration_ms)
        except MPVError:
            pass

    def show_overlay(self, seconds=3.0):
        """Text 'remote control' card matching the touch tap zones."""
        name = self.channels.current_channel_name() or "-"
        card = ("      [ CH + ]      \n"
                "\n"
                "[<%ds]  [play/pause]  [%ds>]\n"
                "\n"
                "      [ CH - ]      \n"
                "\n"
                "ch: %s   hold: power"
                % (self.cfg.get("touch", {}).get("seek_step", 30),
                   self.cfg.get("touch", {}).get("seek_step", 30), name))
        self.osd(card, int(seconds * 1000))

    # -- mpv events -----------------------------------------------------------

    def _on_mpv_event(self, event):
        if event.get("event") != "end-file":
            return
        reason = event.get("reason", "eof")
        if reason not in ("eof", "error"):
            return  # "stop" fires when *we* replace the file; ignore it
        with self._lock:
            was_static = self.playing_static
            self.playing_static = False
        # advance in a thread so we never block the IPC reader
        threading.Thread(target=self._play_next_episode,
                         daemon=True, name="advance").start()

    # -- playback ---------------------------------------------------------------

    def _play(self, path, is_static=False):
        with self._lock:
            self.playing_static = is_static
            self.current_file = path
        try:
            self.mpv.loadfile(path)
        except MPVError as e:
            print("[tv] loadfile failed: %s" % e)

    def _play_next_episode(self):
        ep = self.channels.next_episode()
        if ep is None:
            print("[tv] no videos found in %s — waiting" %
                  self.cfg["videos_dir"])
            time.sleep(5)
            self.channels.rescan()
            ep = self.channels.next_episode()
            if ep is None:
                return
        self._play(ep)

    def next_episode(self):
        self._play_next_episode()

    def _tune(self):
        """Channel changed: show static, then first episode of new channel."""
        static = self.cfg.get("static_clip")
        if static and os.path.exists(static):
            self._play(static, is_static=True)
        else:
            self._play_next_episode()

    # -- controls (used by GPIO + web) -----------------------------------------

    def toggle_pause(self):
        try:
            paused = not self.mpv.get("pause", False)
            self.mpv.set("pause", paused)
            self.osd("|| paused" if paused else "> play")
        except MPVError:
            pass

    def toggle_power(self):
        self.power = not self.power
        self.hw.set_power(self.power)
        try:
            self.mpv.set("pause", not self.power)
        except MPVError:
            pass

    def change_channel(self, step=1):
        name = self.channels.change_channel(step)
        if name is not None:
            self.osd("ch %d  %s" % (self.channels.index + 1, name))
            self._tune()

    def set_channel(self, name):
        if self.channels.set_channel(name) is not None:
            self.osd("ch %d  %s" % (self.channels.index + 1, name))
            self._tune()

    def seek(self, seconds):
        if self.playing_static:
            return
        try:
            self.mpv.command("seek", seconds, "relative")
            self.osd("%+ds" % seconds)
        except MPVError:
            pass

    def set_volume(self, volume):
        vol = self.channels.set_volume(volume)
        try:
            self.mpv.set("volume", vol)
        except MPVError:
            pass
        self.osd("vol %d" % vol)

    def status(self):
        now = None
        if self.current_file:
            now = ("~ static ~" if self.playing_static
                   else os.path.splitext(os.path.basename(self.current_file))[0])
        return {
            "power": self.power,
            "paused": bool(self.mpv.get("pause", False)),
            "now_playing": now,
            "channel": self.channels.current_channel_name(),
            "channels": self.channels.channel_names(),
            "volume": self.channels.volume,
        }

    # -- watchdog ----------------------------------------------------------------

    def watch(self):
        while True:
            time.sleep(5)
            if not self.mpv.alive():
                print("[tv] mpv died — restarting it")
                try:
                    self.mpv = MPV(extra_args=self.cfg.get("mpv_args", []),
                                   event_handler=self._on_mpv_event)
                    self.mpv.start()
                    self.mpv.set("volume", self.channels.volume)
                    self._play_next_episode()
                except MPVError as e:
                    print("[tv] mpv restart failed: %s" % e)


def main():
    cfg = load_config()
    tv = TV(cfg)
    tv.start()

    app = create_app(tv)
    web = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=cfg["web_port"],
                               threaded=True, use_reloader=False),
        daemon=True, name="webui")
    web.start()
    print("[tv] running — web remote on port %s" % cfg["web_port"])

    try:
        tv.watch()
    except KeyboardInterrupt:
        tv.mpv.stop()


if __name__ == "__main__":
    main()
