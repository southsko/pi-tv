#!/bin/bash
# Simpsons TV installer — the non-interactive core. Run ON the Pi:
#   bash install.sh
# Installs packages, the systemd service, the power-loss self-heal, and the
# `tvctl` command. setup.sh calls this, then runs the interactive configurator.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
GOLDEN="${DIR}-golden"

echo "==> Installing packages (mpv, flask, gpiozero, ffmpeg, git)..."
sudo apt update
sudo apt install -y mpv python3-flask python3-gpiozero python3-evdev ffmpeg git

echo "==> Creating videos folder structure..."
mkdir -p "$DIR/videos/simpsons"

if [ ! -f "$DIR/static.mp4" ]; then
  echo "==> Generating TV static clip (static.mp4)..."
  bash "$DIR/make_static.sh"
fi

echo "==> Making scripts executable..."
chmod +x "$DIR"/*.sh "$DIR"/pitv_config.py 2>/dev/null || true

echo "==> Installing systemd service..."
sed "s|/home/pi/simpsonstv|$DIR|g; s|User=pi|User=$USER|g" \
  "$DIR/simpsonstv.service" | sudo tee /etc/systemd/system/simpsonstv.service >/dev/null

echo "==> Setting up the power-loss self-heal golden copy at $GOLDEN ..."
mkdir -p "$GOLDEN"
cp -a "$DIR"/*.py "$GOLDEN"/ 2>/dev/null || true
cp -a "$DIR"/heal.sh "$DIR"/pitv_lib.sh "$DIR"/configure.sh "$DIR"/tvctl.sh "$GOLDEN"/ 2>/dev/null || true
[ -f "$DIR/static.mp4" ] && cp -a "$DIR/static.mp4" "$GOLDEN"/
[ -f "$DIR/config.json" ] && cp -a "$DIR/config.json" "$GOLDEN"/
chmod +x "$GOLDEN/heal.sh" 2>/dev/null || true
sync

echo "==> Keeping logs in RAM so unclean power-off can't corrupt the card..."
sudo sed -i 's/^#\?Storage=.*/Storage=volatile/' /etc/systemd/journald.conf
grep -q '^Storage=volatile' /etc/systemd/journald.conf || \
  echo 'Storage=volatile' | sudo tee -a /etc/systemd/journald.conf >/dev/null

echo "==> Installing the 'tvctl' command..."
sudo tee /usr/local/bin/tvctl >/dev/null <<EOF
#!/bin/bash
PITV_DIR="$DIR"
export PITV_DIR
exec bash "\$PITV_DIR/tvctl.sh" "\$@"
EOF
sudo chmod +x /usr/local/bin/tvctl

echo "==> Installing the login MOTD (web/share URLs, resolved live)..."
sed "s|/home/pi/simpsonstv|$DIR|g" "$DIR/motd.sh" | sudo tee /etc/update-motd.d/99-pitv >/dev/null
sudo chmod +x /etc/update-motd.d/99-pitv

sudo systemctl daemon-reload
sudo systemctl restart systemd-journald 2>/dev/null || true
sudo systemctl enable simpsonstv

echo
echo "Core install done."
echo "  Put .mp4 files in $DIR/videos/<channel-name>/"
echo "  Control it any time with:  tvctl status   |   tvctl reconfigure"
echo "  Start now:  sudo systemctl start simpsonstv"
