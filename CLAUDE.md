# Pi TV — handoff notes for Claude Code

Context for continuing work on this project. Repo: `southsko/pi-tv`.
A modernized "Simpsons TV": a Raspberry Pi plays random episodes on a small
screen like an always-on TV. Rewrite of the dead `buba447/simpsonstv`
(omxplayer) using mpv. Full user docs are in `README.md` — read it first.

## Where it runs
- **Target device:** Raspberry Pi Zero W / Zero 2 W, Raspberry Pi OS Lite
  (Bookworm/Trixie), hostname `simpsonstv` (`ssh joey@simpsonstv.local`).
  Project installed at `~/pi-tv`. Runs as systemd service `simpsonstv`.
- **Converter tools** (`tools/`) run on a PC/Unraid box, NOT the Pi.

## Architecture (on the Pi)
- `tv.py` — main service. Owns state, mpv, hardware, touch, web thread.
- `mpv_ipc.py` — talks to mpv over a JSON IPC unix socket (stdlib only).
- `channels.py` — each subfolder of `videos/` is a channel; shuffles without
  repeats; persists channel+volume to `state.json`.
- `hardware.py` — gpiozero buttons + `pinctrl` backlight/audio/amp. No-ops
  gracefully off-Pi so `python3 tv.py` works on any Linux for testing.
- `touch.py` — evdev touchscreen gestures (tap overlay, swipe, zone-aware hold).
- `webui.py` — Flask remote + file manager on port 8080.
- `config.json` — all tunables (see README "Configuration reference").

## Setup scripts
`setup.sh` orchestrates: `install.sh` (packages+service), `setup_screen.sh`
(Waveshare 2.8" DPI overlays + audio), `setup_share.sh` (Samba), `setup_exfat.sh`
(grow root, mount exFAT data partition). `speedup_boot.sh` trims boot. Windows
card-prep: `partition_card.ps1` / `prepare_card.ps1`.

## Hard-won gotchas (things that already bit us — don't re-break)
- **GPIO map is specific to the Waveshare 2.8" DPI screen:** backlight = GPIO 18,
  PWM audio = GPIO 19, power button = GPIO 26. No free pin for a channel button.
- **Audio:** needs `dtoverlay=audremap,enable_jack,pins_18_19` AND
  `/etc/asound.conf` pointing ALSA default at the `Headphones` card (block form,
  not `defaults.pcm.card`). Amp needs the A−→GND jumper.
- **Rotation:** panel is portrait; mpv `--video-rotate=270` is the default, and
  `touch.rotate` + `osd_rotate` must match it. OSD is drawn via ASS `\an5` so it
  centers at any resolution.
- **Hardware decode:** playback uses `--hwdec=v4l2m2m-copy` (the Zero's VideoCore
  H.264 decoder) — the KMS/mpv software path is too slow on a Zero.
- **Desktop image:** if flashed Desktop not Lite, the greeter steals the screen;
  `setup.sh` sets `multi-user.target` + disables lightdm.
- **Boot backlight:** kept off (`gpio=18=op,dl`) until the service turns it on.
- **❌ Never enable overlayfs / `overlayroot` on this board.** It hangs on the
  first boot (Waveshare DPI + initramfs) and needs an SD-card pull to recover.
  See "Power-loss hardening" below — the unplug problem is already solved without
  it.

## Power-loss hardening (unplug-safe) — don't re-break
Portable USB-powered unit, unplugged with no clean shutdown. An unclean power-off
once zeroed `tv.py` (0 bytes) on the ext4 root and crash-looped the service. Fix
in place (runtime only, no boot-path changes — verified by zeroing `tv.py` +
cold boot):
- **Self-heal:** service has `ExecStartPre=/bin/bash /home/joey/pi-tv-golden/heal.sh`.
  On every start it restores any `*.py` / `static.mp4` / `config.json` that is
  missing, zero-length, or non-compiling from the golden copy at
  `/home/joey/pi-tv-golden/`. Always exits 0 so it can't block startup.
- **After editing device files, refresh the golden copy** or the change isn't
  protected (and a syntax error gets rolled back next start):
  `cp -a /home/joey/pi-tv/*.py /home/joey/pi-tv/static.mp4 /home/joey/pi-tv/config.json /home/joey/pi-tv-golden/ && sync`
- `journald` `Storage=volatile` (logs in RAM, no SD writes during operation).
- `state.json` is on the journaled ext4 root (atomic write), `state_file` in
  `config.json` — deliberately NOT on the exFAT `videos/` partition, so playback
  never writes to the video library.
- Login MOTD lives at `/etc/update-motd.d/99-pitv` (dynamic; resolves IP live).

## Converter (`tools/pi_convert.py`) — GPU notes
- Auto-detects NVENC/QSV/AMF by test-encoding a 320x240 frame (64x64 fails
  NVENC's min size — don't shrink it). Ampere+ NVENC dropped H.264 *baseline*,
  so GPU paths use **high** profile (Pi decodes high fine).
- Pipeline ladder per file: full CUDA (NVDEC+scale_cuda+NVENC) → GPU encode only
  → CPU decode+NVENC → CPU. Falls back automatically.
- On Unraid: needs the **Nvidia Driver** plugin (`nvidia-smi`) and an ffmpeg
  build WITH nvenc (BtbN builds; John Van Sickle static lacks it).
- CLI mode (headless): `python3 pi_convert.py <folder> -o <out>` — no browser.
  Interactive: curses browser (primary), ANSI fallback, GUI on Windows.

## Working on the Pi
- Restart after changes: `sudo systemctl restart simpsonstv`
- Logs: `journalctl -u simpsonstv -f`
- Test playback logic off-device: `python3 tv.py` on any Linux w/ mpv.
- Deploy edits: `cd ~/pi-tv && git pull`, **refresh the golden copy** (see
  "Power-loss hardening"), then restart. Or edit in place + refresh golden.

## Git
`main` branch, push to `github.com/southsko/pi-tv`. Keep changes small and
committed with clear messages. Don't commit `state.json`, `static.mp4`, or
`videos/` (see `.gitignore`).
