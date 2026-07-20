#!/bin/bash
# Simpsons TV installer — run ON the Pi as user pi:
#   bash install.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing packages (mpv, flask, gpiozero, ffmpeg)..."
sudo apt update
sudo apt install -y mpv python3-flask python3-gpiozero ffmpeg

echo "==> Creating videos folder structure..."
mkdir -p "$DIR/videos/simpsons"

if [ ! -f "$DIR/static.mp4" ]; then
  echo "==> Generating TV static clip (static.mp4)..."
  bash "$DIR/make_static.sh"
fi

echo "==> Installing systemd service..."
sed "s|/home/pi/simpsonstv|$DIR|g; s|User=pi|User=$USER|g" \
  "$DIR/simpsonstv.service" | sudo tee /etc/systemd/system/simpsonstv.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable simpsonstv

echo
echo "Done. Put .mp4 files in $DIR/videos/<channel-name>/ then:"
echo "  sudo systemctl start simpsonstv"
echo "Web remote: http://$(hostname).local:8080"
