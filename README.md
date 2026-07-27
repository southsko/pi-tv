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
| — | Touchscreen gestures + on-screen overlay (the Waveshare 2.8" panel is capacitive touch) |
| — | Web remote + file manager: play/pause, skip, channel, volume, upload/rename/delete from your phone |
| — | Remembers channel + volume across reboots |
| — | exFAT data partition option (pop the card in Windows, drag episodes on) |
| — | GPU-accelerated batch converter (`tools/pi_convert.py`) for prepping your library |

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
   It installs packages, the static-effect clip, the systemd service and the
   power-loss self-heal, then opens a **menu** (whiptail) where you pick the
   screen, rotation, Samba share on/off, exFAT, web port, and volume — no file
   editing. Re-run `bash setup.sh`, or `tvctl reconfigure`, to change things
   later.
   Want the exFAT card-in-Windows option? Do the `prepare_card.ps1` step right
   after flashing, *before* first boot — see "exFAT partition" below.
3. Add episodes (each subfolder = one channel):
   ```
   videos/simpsons/S01E01.mp4
   videos/futurama/...
   videos/commercials/...
   ```
   Episodes should be 480p H.264 with AAC audio for smooth hardware-decoded
   playback — see **Converting your videos** below for the tools that do this.

The individual scripts (`install.sh`, `setup_share.sh`, `setup_exfat.sh`,
`setup_screen.sh`, `speedup_boot.sh`) can also be run on their own if you prefer
piecemeal setup. `setup.sh` also switches a Desktop image to console boot so the
desktop can't fight mpv for the screen.

## Converting your videos

Source files (1080p, EAC3 5.1, etc.) won't play well on the Pi. Convert them to
480p H.264 baseline + stereo AAC first — **on a real computer, never the Pi**
(the Zero would take hours). Two tools in `tools/`:

**`pi_convert.py` — interactive + scriptable, GPU-accelerated (recommended).**
Auto-detects an NVIDIA/Intel/AMD GPU and uses hardware encode+decode (NVENC +
NVDEC), falling back to CPU cleanly. Shows a live per-file progress bar with
fps, speed, and a whole-queue ETA. Skips files already done, so it's safe to
re-run.

- **Just point it at folders (best for headless / Unraid / SSH):**
  ```bash
  python3 pi_convert.py "/path/to/The Simpsons" -o "/path/to/output"
  ```
  Converts every video under the folder (recursively, skipping "sample" files),
  no menus.
- **Interactive picker (no arguments):** a DOS-style file browser — arrows to
  move, **Space** to tag a file or a whole folder (all episodes inside), **Enter**
  to open, **F2** to convert, then choose/create the output folder. On Windows it
  uses a native file dialog if the terminal browser isn't available.

Requirements: `ffmpeg`/`ffprobe` on PATH. For GPU on Linux/Unraid use a build
with NVENC (e.g. [BtbN's builds](https://github.com/BtbN/FFmpeg-Builds)) — some
static builds omit it. On Unraid you also need the **Nvidia Driver** plugin so
`nvidia-smi` works. Quality knobs via env: `CRF=20`, `HEIGHT=480`, `PRESET=fast`.

**`encode.py` — simple batch, CPU.** Drop it next to source videos, run
`python3 encode.py`; it walks all subfolders, flattens output into `./encoded/`,
and skips samples. Good when you don't need the GPU or interactivity.

By hand, the equivalent one-liner:
`ffmpeg -i in.mkv -vf scale=-2:480 -c:v libx264 -profile:v baseline -level 3.0 -c:a aac -ac 2 out.mp4`

## Touchscreen

The Waveshare 2.8" DPI panel used in the current build guide has capacitive touch,
which shows up as a normal Linux input device — so the TV itself is a remote:

| Gesture | Default action |
|---|---|
| Tap | Show control overlay; while visible, taps hit its zones: top = CH+, bottom = CH-, left/right = seek, center = pause |
| Swipe up / down | Next / previous channel (with static effect) |
| Swipe left / right | Seek -30s / +30s |
| Hold right | **Skip** to next episode (plays the static transition) |
| Hold center | Power toggle |

The overlay stays up for `overlay_s` seconds (default 3) and refreshes on each
tap, so you can chain channel taps. Prefer plain tap-to-pause? Set
`touch.gestures.tap` to `"pause"`.

Long-press is **zone-aware** — `hold_left/right/top/bottom/center` in
`config.json` (`touch.gestures`) each take any action: `pause`, `power`,
`channel_up`, `channel_down`, `volume_up`, `volume_down`, `next_episode`,
`skip` (next episode with static), `seek_fwd`, `seek_back`, `overlay`, `none`.
Taps and swipes are remappable the same way. Handy if you have the physical
volume knob and want gestures for other things.

Feedback appears as an on-screen OSD (channel name, volume, pause), drawn
rotated to match the video. In `config.json`: `touch.rotate` and `osd_rotate`
should match your `--video-rotate` (all default to **270** for the standard
portrait-mounted build; if it's upside-down or swipes feel backwards, try 90).
`osd_font_size` sizes the overlay text; `static_volume` (default 40) sets how
loud the channel-change static plays vs normal programming. `touch.enabled:
false` turns touch off. Physical buttons remain optional and work alongside
touch.

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

## Changing settings — `tvctl` and the menu

You normally never touch `config.json` by hand. Two front-ends write it for you
(and keep it valid JSON, refresh the self-heal golden copy, and restart the TV):

- **`tvctl reconfigure`** — the full whiptail menu (same one `setup.sh` opens).
- **`tvctl <cmd>`** — one-liners, e.g.:
  ```bash
  tvctl status                 # service state, settings, web + share URLs
  tvctl rotate 90              # rotation (video+touch+framebuffer together)
  tvctl volume 60              # channel-change static loudness
  tvctl port 8000              # web remote port
  tvctl samba on | off         # network share of the videos folder
  tvctl update                 # git pull + refresh golden copy + restart
  tvctl logs                   # follow the log
  ```
  `tvctl rotate` sets `osd_rotate`, `touch.rotate`, the mpv `--video-rotate`
  flag **and** the framebuffer `rotate=` in `cmdline.txt` in one shot (the
  framebuffer part needs a reboot). See "Power-loss hardening" for why editing
  files directly means you should also run `tvctl golden` afterward.

## Configuration reference

Everything lives in `config.json`. Prefer `tvctl` / the menu over editing it by
hand; if you do edit it, run `tvctl golden` then `sudo systemctl restart
simpsonstv`. Defaults shown.

| Key | Default | What it does |
|---|---|---|
| `web_port` | `8080` | Port for the web remote/file manager |
| `static_volume` | `40` | Volume (0–130) of the channel-change static vs normal programming |
| `power_switch_mode` | `"toggle"` | `"switch"` if you wired a slide switch instead of a pushbutton |
| `osd_rotate` | `270` | Rotation of the on-screen overlay text; match `--video-rotate` |
| `osd_font_size` | `36` | Overlay text size |
| `touch.enabled` | `true` | Turn the touchscreen on/off |
| `touch.rotate` | `270` | Maps touch coords to the rotated display (`90`/`180`/`270`) |
| `touch.swipe_px` | `80` | Pixels of movement before a tap counts as a swipe |
| `touch.long_press_s` | `0.8` | Seconds held to count as a long-press |
| `touch.seek_step` | `30` | Seconds for a seek gesture |
| `touch.overlay_s` | `3.0` | How long the control overlay stays up |
| `touch.gestures.*` | see above | Remap `tap`, `up/down/left/right`, `hold_left/right/top/bottom/center` |
| `pins.power_button` | `26` | GPIO for the power button (`null` = none) |
| `pins.channel_button` | `null` | Optional channel button (no free pin on the Waveshare screen) |
| `pins.backlight` | `18` | Screen backlight enable |
| `pins.audio_pwm` | `19` | PWM audio output pin |
| `pins.amp_enable` | `null` | Optional amp enable/shutdown pin |
| `mpv_args` | (list) | Raw mpv flags — rotation, `--hwdec`, `--vo`, volume normalization, etc. |
| `videos_dir` | `videos/` | Where channels/episodes live (the exFAT mount point when used) |

**Environment variables** (set before running a script):

| Var | Used by | Effect |
|---|---|---|
| `ROTATE` | `setup_screen.sh` | Framebuffer rotation to write to `cmdline.txt` (default `270`) |
| `ZERO_FIX=1` | `setup_screen.sh` | Apply the Pi Zero 2 W green-tint overlay fix |
| `HEIGHT`, `CRF`, `PRESET` | `pi_convert.py`, `encode.py` | Output height, quality (lower = better/bigger), x264 speed |
| `SKIP` | `encode.py` | Comma-separated words to ignore (default `sample`) |
| `PI_TV_OUT` | `pi_convert.py` | Preset output folder (skips the prompt) |
| `PI_TV_GUI=1` / `PI_TV_TUI=1` | `pi_convert.py` | Force the native GUI / force the terminal browser |

## Files

- `tv.py` — main service (start here)
- `mpv_ipc.py` — minimal mpv JSON-IPC client, no pip dependencies
- `channels.py` — channel/shuffle/state logic
- `hardware.py` — buttons, backlight, amp (safe no-op off-Pi)
- `touch.py` — touchscreen gestures (evdev)
- `webui.py` — Flask web remote + file manager
- `config.json` — pins, port, mpv flags, touch gestures, rotation
- `tvctl.sh` — the `tvctl` control command (installed to `/usr/local/bin/tvctl`)
- `configure.sh` — whiptail settings menu (`tvctl reconfigure`)
- `pitv_config.py` — validates/writes `config.json`; keeps rotation keys in sync
- `pitv_lib.sh` — shared shell helpers for the installer and `tvctl`
- `heal.sh` — power-loss self-heal (service `ExecStartPre`; lives in the golden copy)
- `setup.sh` — one-shot installer (calls the rest, then the menu)
- `install.sh`, `simpsonstv.service` — core install
- `setup_screen.sh` — Waveshare 2.8" DPI screen + audio config
- `setup_share.sh` — Samba share
- `setup_exfat.sh` — grow root + mount exFAT data partition
- `speedup_boot.sh` — trims services, WiFi power-save, boot splash
- `make_static.sh` — regenerates the static-effect clip
- `partition_card.ps1` / `prepare_card.ps1` — Windows exFAT card prep
- `tools/pi_convert.py`, `tools/encode.py` — video converters (see above)

## Testing without a Pi

`python3 tv.py` runs on any Linux box with mpv installed — GPIO calls become
no-ops and mpv opens a window. Handy for testing channels and the web UI.

## Power-loss hardening (unplug-safe) — read before modifying the device

This is a portable, USB-powered unit that gets **unplugged with no clean
shutdown**. An unclean power-off can leave the SD card's ext4 root with
half-written data — which once zeroed `tv.py` and left the service crash-looping.
The measures below make it survive a yank. Understand them before you change
**anything on the device**, because the self-heal can roll a bad edit back.

- **Self-heal on boot.** `simpsonstv.service` runs an `ExecStartPre` hook
  (`/home/joey/pi-tv-golden/heal.sh`) that, on every start, restores any app
  source file (`*.py`, `static.mp4`, `config.json`) that is **missing,
  zero-length, or fails to compile** from a golden copy at
  `/home/joey/pi-tv-golden/`. A corrupted file therefore fixes itself on the next
  boot — verified by zeroing `tv.py` and cold-booting.
- **⚠️ After editing app/config files on the device, refresh the golden copy** —
  otherwise your change isn't protected, and if the edit has a syntax error it is
  **rolled back** to the golden version on the next start:
  ```bash
  cp -a /home/joey/pi-tv/*.py /home/joey/pi-tv/static.mp4 \
        /home/joey/pi-tv/config.json /home/joey/pi-tv-golden/ && sync
  ```
  A *valid* edit is never reverted (heal only triggers on missing/empty/broken
  files), but keeping golden current means a future corruption restores your
  latest version, not an old one.
- **Logs go to RAM.** `journald` is set to `Storage=volatile`, so nothing is
  written to the SD card for logging during normal operation. `journalctl` shows
  the current boot only; logs don't persist across reboot.
- **State on the journaled root.** `state.json` (last channel + volume) is written
  atomically to the ext4 root (power-safe), **not** to the exFAT video partition —
  so playback performs no writes to the video partition and a yank can't corrupt
  your episode library.
- **❌ Do NOT enable the overlay filesystem** (`raspi-config` → Performance →
  Overlay FS, or the `overlayroot` package). It hangs on the first boot on this
  Waveshare DPI board. If it ever gets enabled and the Pi won't boot: power off,
  pull the SD card, open the `bootfs` (FAT) partition on another computer, remove
  `overlayroot=tmpfs` from `cmdline.txt`, change `auto_initramfs=1` to
  `#auto_initramfs=1` in `config.txt` (save as plain ASCII, **no BOM**), reinsert,
  and boot.

A short version of this — plus the live web-remote and Samba URLs — is shown as
the SSH message-of-the-day (`/etc/update-motd.d/99-pitv`, IP resolved at login so
it's DHCP-safe).

**Modifying the system safely:** the root is ordinary read-write ext4 — edit
files and install packages as usual; the only special rule is the golden-copy
refresh above. Run `sudo sync` before unplugging after any significant change, and
prefer to unplug while idle. To deploy from git: `cd ~/pi-tv && git pull`, refresh
the golden copy, then `sudo systemctl restart simpsonstv`.

## Troubleshooting

- Video sideways/upside-down: mpv rotates the portrait panel via
  `--video-rotate` in `config.json`'s `mpv_args` (default **270**). Try `90` if
  it's flipped, and set `touch.rotate` + `osd_rotate` to match.
- No sound: check `aplay -l` shows a `Headphones` card; `/etc/asound.conf` must
  point ALSA's default at it (setup_screen.sh writes this). The audremap overlay
  needs `enable_jack`. `speaker-test -D default -t sine` is a quick check.
- Choppy / low framerate playback: the source isn't 480p, or hardware decode
  isn't active. Re-encode with the converter (see **Converting your videos**);
  playback uses `--hwdec=v4l2m2m-copy` (the Pi's hardware H.264 decoder).
- Boots to a desktop / greeter steals the screen: you flashed Desktop, not Lite.
  `sudo systemctl set-default multi-user.target && sudo systemctl disable lightdm`
  (or just run `setup.sh`, which does this).
- Black screen but audio plays: check `mpv_args`. On some setups `--vo=drm` beats
  `--vo=gpu --gpu-context=drm`. A bare-panel white screen at boot is normal until
  the player takes over (setup keeps the backlight off until then).
- Backlight doesn't switch: your display may use a different enable pin; adjust
  `pins.backlight`.
- SSH laggy / drops: Zero W WiFi power-save — `speedup_boot.sh` disables it.
- Logs: `journalctl -u simpsonstv -f`
- Slow boot: run `bash speedup_boot.sh` (disables bluetooth/printing, removes the
  boot splash, starts the player before the network). Lite boots far faster than
  Desktop. Profile stragglers with `systemd-analyze blame`.
