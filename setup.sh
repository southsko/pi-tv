#!/bin/bash
# One-shot setup. On a fresh default Raspberry Pi OS install:
#
#   sudo apt update && sudo apt install -y git
#   git clone https://github.com/southsko/pi-tv.git ~/pi-tv
#   cd ~/pi-tv && bash setup.sh
#
# Installs everything (packages, service, power-loss self-heal, tvctl), then
# opens a menu to pick the screen, rotation, Samba share, exFAT, etc.
# Re-run any time, or use `tvctl reconfigure`, to change things later.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=========================================="
echo "  Pi TV setup"
echo "=========================================="

bash install.sh

# The TV plays straight to the display from the console (DRM) - a desktop
# session just wastes the Zero's RAM and fights over the screen.
if [ "$(systemctl get-default)" = "graphical.target" ]; then
  echo "==> Desktop image detected - switching to console boot (desktop stays installed)"
  sudo systemctl set-default multi-user.target
fi

# Smart interactive configuration (rotation, screen, Samba, exFAT, ports...).
echo "==> Opening the configuration menu..."
PITV_DIR="$DIR" bash "$DIR/configure.sh" || true

echo "==> Starting the TV..."
sudo systemctl restart simpsonstv

HOST="$(hostname)"
PORT="$(PITV_CONFIG="$DIR/config.json" python3 "$DIR/pitv_config.py" get web_port)"
echo
echo "=========================================="
echo "  Done!"
echo "  Videos:      $DIR/videos/<channel>/"
echo "  Web remote:  http://$HOST.local:${PORT:-8080}"
echo "  Net share:   \\\\$HOST\\videos   (if Samba enabled)"
echo "  Control:     tvctl status | tvctl reconfigure"
echo "  Logs:        tvctl logs"
echo "=========================================="
echo
echo "If you configured the screen or switched off the desktop, reboot once:  sudo reboot"
