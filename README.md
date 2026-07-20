# Simpsons TV — Modernized

An updated take on [buba447/simpsonstv](https://github.com/buba447/simpsonstv) for the
Raspberry Pi Zero 2 W and current Raspberry Pi OS (Trixie, works on Bookworm too). The original relied on
`omxplayer`, which was removed from Raspberry Pi OS years ago — this version uses mpv
and adds channels, a channel-change static effect, and a web remote.

## What's new vs. the original

| Original | This version |
|---|---|
| omxplayer (dead since Bullseye) | mpv via JSON IPC, hardware decode |
| Two scripts + rc.local | One service managed by systemd |
| RPi.GPIO + raspi-gpio (both deprecated) | gpiozero + pinctrl |
| One shuffled folder | Channels: every subfolder of `videos/` is a channel |
| — | TV-static effect when changing channels |
| — | Touchscreen gestures (the Waveshare 2.8" panel is capacitive touch) |
| — | Web remote: play/pause, skip, channel, volume, upload episodes from your phone |
| — | Remembers channel + volume across reboots |

## Hardware

Same electronics as the [original build guide](https://withrow.io/simpsons-tv-build-guide),
but use a **Pi Zero 2 W**. Default wiring (BCM numbering, configurable in `config.json`):

| Pin | Function |
|---|---|
| GPIO 26 | Power button (to GND) |
| GPIO 20 | Channel button (to GND) — new, optional |
| GPIO 19 | Display backlight enable |
| GPIO 18 | Audio amp enable/shutdown |

Power button pauses playback and cuts the backlight + amp, like the original.
If you use a slide switch instead of a pushbutton, set `"power_switch_mode": "switch"`
in `config.json`.

## Install

1. Flash **Raspberry Pi OS Lite** (Trixie or Bookworm) with WiFi + SSH configured.
2. Copy this folder to the Pi: `scp -r . pi@simpsonstv.local:~/simpsonstv`
3. On the Pi:
   ```bash
   cd ~/simpsonstv
   bash install.sh
   ```
4. Add episodes (each subfolder = one channel):
   ```
   videos/simpsons/S01E01.mp4
   videos/futurama/...
   videos/commercials/...
   ```
   For the Zero 2 W, encode to 480p H.264 for smooth playback:
   `ffmpeg -i in.mkv -vf scale=640:480 -c:v libx264 -profile:v high -level 4.0 -c:a aac out.mp4`
5. `sudo systemctl start simpsonstv`

## Touchscreen

The Waveshare 2.8" DPI panel used in the current build guide has capacitive touch,
which shows up as a normal Linux input device — so the TV itself is a remote:

| Gesture | Default action |
|---|---|
| Tap | Show control overlay; while visible, taps hit its zones: top = CH+, bottom = CH-, left/right = seek, center = pause |
| Swipe up / down | Next / previous channel (with static effect) |
| Swipe left / right | Seek -30s / +30s |
| Long press (0.8s) | Power toggle |

The overlay stays up for `overlay_s` seconds (default 3) and refreshes on each
tap, so you can chain channel taps. Prefer plain tap-to-pause? Set
`touch.gestures.tap` to `"pause"`.

Every gesture is remappable in `config.json` (`touch.gestures`) to any of:
`pause`, `power`, `channel_up`, `channel_down`, `volume_up`, `volume_down`,
`next_episode`, `seek_fwd`, `seek_back`, `none` — handy if you have the
physical volume knob and want gestures for something else.

Feedback appears as an on-screen OSD (channel name, volume). Configure in
`config.json` under `touch` — set `rotate` to match your `display_rotate`
(90 is right for the standard portrait-mounted build; if swipes feel
backwards, try 270), or `enabled: false` to turn it off. Physical buttons
remain optional and work alongside touch.

## Web remote + file manager

Open `http://simpsonstv.local:8080` on your phone (same WiFi). You can play/pause,
skip, change channel, set volume, and upload new episodes (multi-file) straight into
a channel — no more pulling the SD card. The Files panel lists every channel's
episodes with sizes and free disk space, and lets you rename, delete, and create
channel folders. Note: no authentication, so it's open to anyone on your network;
keep it on your home LAN.

## Getting files on (Samba / SFTP)

- **Network drive (recommended):** run `bash setup_share.sh` once, then the videos
  folder appears as `\\simpsonstv\videos` on Windows / `smb://simpsonstv.local/videos`
  on Mac. Drag episodes in; each subfolder is a channel. Guest read+write. After
  setup, the share can be switched on/off from the web UI (the setup script adds a
  narrow sudoers rule so the service can start/stop smbd — nothing else).
- **SFTP:** works out of the box over SSH — point FileZilla/WinSCP at
  `simpsonstv.local`, user `pi`, and drop files into `~/simpsonstv/videos/`.
  (Skip plain FTP — it's unencrypted and needs extra server setup for no benefit.)

## Files

- `tv.py` — main service (start here)
- `mpv_ipc.py` — minimal mpv JSON-IPC client, no pip dependencies
- `channels.py` — channel/shuffle/state logic
- `hardware.py` — buttons, backlight, amp (safe no-op off-Pi)
- `webui.py` — Flask web remote
- `config.json` — pins, port, mpv flags
- `make_static.sh` — regenerates the static-effect clip
- `install.sh`, `simpsonstv.service` — setup

## Testing without a Pi

`python3 tv.py` runs on any Linux box with mpv installed — GPIO calls become
no-ops and mpv opens a window. Handy for testing channels and the web UI.

## Troubleshooting

- Black screen but audio plays: check `mpv_args` in `config.json`. On some display
  setups `--vo=drm` works better than `--vo=gpu --gpu-context=drm`.
- Backlight doesn't switch: your display may use a different enable pin; adjust
  `pins.backlight`.
- Logs: `journalctl -u simpsonstv -f`
