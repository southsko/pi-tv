#!/bin/bash
# One-shot setup. On a fresh default Raspberry Pi OS install:
#
#   sudo apt update && sudo apt install -y git
#   git clone https://github.com/southsko/pi-tv.git ~/pi-tv
#   cd ~/pi-tv && bash setup.sh
#
# Does everything: packages, static clip, Samba share, exFAT data partition
# (if the card has one), systemd service — and starts the TV.
#
# Flags (env vars):  SKIP_SAMBA=1  SKIP_EXFAT=1
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=========================================="
echo "  Pi TV setup"
echo "=========================================="

bash install.sh

if [ -z "$SKIP_SAMBA" ]; then
  bash setup_share.sh
else
  echo "==> Skipping Samba (SKIP_SAMBA set)"
fi

if [ -z "$SKIP_EXFAT" ]; then
  DEV=/dev/mmcblk0
  if sudo blkid -t TYPE=exfat -o device 2>/dev/null | grep -q "^$DEV" \
     || { [ -b "${DEV}p3" ] && ! sudo blkid "${DEV}p3" >/dev/null 2>&1; }; then
    bash setup_exfat.sh
  else
    echo "==> No exFAT/data partition on the card — skipping."
    echo "    (Only possible on a freshly flashed card, before first boot:"
    echo "     see 'exFAT partition' in the README. Samba/SFTP/web uploads"
    echo "     all work regardless.)"
  fi
fi

echo "==> Starting the TV..."
sudo systemctl restart simpsonstv

echo
echo "=========================================="
echo "  Done!"
echo "  Videos:      $DIR/videos/<channel>/"
echo "  Web remote:  http://$(hostname).local:8080"
echo "  Net share:   \\\\$(hostname)\\videos"
echo "  Logs:        journalctl -u simpsonstv -f"
echo "=========================================="
