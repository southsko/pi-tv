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

Same electronics as the [Waveshare build guide](https://withrow.io/simpsons-tv-build-guide-waveshare),
but use a **Pi Zero 2 W**:

- **Screen: [Waveshare 2.8" DPI LCD](https://www.waveshare.com/2.8inch-dpi-lcd.htm)**
  (480×640 IPS, capacitive 5-point touch, sits directly on the 40-pin header —
  no soldering). This is the screen the code is configured for out of the box;
  `setup_screen.sh` (run automatically by `setup.sh`) installs the overlays and
  config per the [Waveshare wiki](https://www.waveshare.com/wiki/2.8inch_DPI_LCD),
  including touch and portrait rotation.
- Adafruit Mono 2.5W amp (PAM8302) + 1.5" 4Ω speaker + 1K volume pot
- Micro pushbutton for power, micro-USB breakout for the power jack
- Enclosure STLs: [Thingiverse thing:4943159](https://www.thingiverse.com/thing:4943159)

Wiring (BCM numbering — the DPI screen occupies nearly every GPIO, these are
the only free ones, confirmed against the Waveshare pinout):

| Pin | Function |
|---|---|
| GPIO 26 | Power button (to GND) |
| GPIO 18 | Screen backlight (driven high = on; screen's own control pin) |
| GPIO 19 | PWM audio out — wire to the amp's audio in |

There is **no spare pin** for a channel button or amp-enable with this screen —
channel changes are touch/web-remote territory. On other displays with free
GPIOs you can set `channel_button` / `amp_enable` in `config.json` (null = off).

Power button behavior: cuts the backlight, mutes audio (GPIO 19 to input),
and pauses playback. Slide switch instead of pushbutton? Set
`"power_switch_mode": "switch"`.

Pi Zero 2 W note: if greys look green on this screen, run
`ZERO_FIX=1 bash setup_screen.sh` (known quirk, Waveshare ships a fixed overlay).

## Install (the easy way)

1. Flash **Raspberry Pi OS Lite** (Trixie or Bookworm) with WiFi + SSH configured
   in the Imager. Boot it, SSH in.
2. Run:
   ```bash
   sudo apt update && sudo apt install -y git
   git clone https://github.com/southsko/pi-tv.git ~/pi-tv
   cd ~/pi-tv && bash setup.sh
   ```
   That's it — packages, static-effect clip, Samba share, systemd service, and
   (if the card has one) the exFAT data partition, all set up and running.
   Want the exFAT card-in-Windows option? Do the `prepare_card.ps1` step right
   after flashing, *before* first boot — see "exFAT partition" below.
   Skip parts with `SKIP_SAMBA=1 bash setup.sh` etc.
3. Add episodes (each subfolder = one channel):
   ```
   videos/simpsons/S01E01.mp4
   videos/futurama/...
   videos/commercials/...
   ```
   For the Zero 2 W, encode to 480p H.264 for smooth playback:
   `ffmpeg -i in.mkv -vf scale=640:480 -c:v libx264 -profile:v high -level 4.0 -c:a aac out.mp4`

The individual scripts (`install.sh`, `setup_share.sh`, `setup_exfat.sh`) can
also be run on their own if you prefer piecemeal setup.

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
- **exFAT partition:** dedicate most of the SD card to an exFAT partition that
  Windows mounts natively — pop the card out, drag episodes on, done. See below.

## exFAT partition (card readable in Windows)

Order matters: this must happen **after flashing but before the Pi's first
boot**. Pi OS normally expands its root partition to fill the whole card on
first boot — all or nothing, no size option — so we either block it or replace it.

### Option A: PowerShell partitioner (recommended)

1. Flash Raspberry Pi OS Lite with the Imager (set WiFi/SSH), leave card in PC.
2. Right-click `partition_card.ps1` → Run with PowerShell. It auto-elevates,
   finds the SD card by its boot files, shows you which disk it found, and on
   confirm creates + formats the exFAT `PITV` partition from the 8 GB mark.
   You can drag episodes onto it immediately.
3. Boot the Pi and run `setup.sh` as usual — it reclaims the 8 GB gap for the
   OS and mounts `PITV` as the videos folder.

### Option B: first-boot automatic (`prepare_card.ps1`)

Same timing as A, but instead of partitioning from Windows it hooks the Imager's
`firstrun.sh` so the Pi partitions itself on first boot (OS capped at 8 GB, rest
becomes the data partition, formatted by `setup.sh`). Requires Imager
customization to be used. Prefer A — it's more deterministic and you can load
episodes before ever booting the Pi.

### Option C: manual (diskpart)

1. Flash Raspberry Pi OS Lite with the Imager (set WiFi/SSH), leave card in PC.
2. Open an **admin** Command Prompt and run `diskpart`:
   ```
   list disk
   select disk X        <- the SD card. CHECK THE SIZE. Wrong disk = data loss.
   create partition primary offset=8388608
   format fs=exfat quick label=PITV
   assign
   exit
   ```
   The `offset` (KB) leaves the first 8 GB for the OS; everything after it
   becomes the exFAT partition. On a 64 GB card that's ~56 GB for episodes.
   You can drag episodes onto the new `PITV` drive right now.
3. Boot the Pi, install as usual, then run: `bash setup_exfat.sh`
   It grows the OS into its reserved 8 GB, mounts the exFAT partition as the
   videos folder permanently, and moves any existing episodes onto it.

Afterwards all roads lead to the same place: card-in-Windows, Samba, SFTP, and
web uploads all land on the exFAT partition. Notes: needs Windows 10 1703+ to
see multiple partitions on an SD card; macOS reads exFAT fine too.

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

- Video sideways/portrait: the panel is natively portrait; mpv rotates it with
  `--video-rotate=90` in `config.json`'s `mpv_args`. Upside down? Use `270`
  (and flip `touch.rotate` to `270` to match).
- No sound: check `aplay -l` shows a `Headphones` card; `/etc/asound.conf` must
  point defaults at it (setup_screen.sh does this). The audremap overlay needs
  `enable_jack`.
- Black screen but audio plays: check `mpv_args` in `config.json`. On some display
  setups `--vo=drm` works better than `--vo=gpu --gpu-context=drm`.
- Backlight doesn't switch: your display may use a different enable pin; adjust
  `pins.backlight`.
- Logs: `journalctl -u simpsonstv -f`
