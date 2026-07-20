#!/bin/bash
# Mounts an exFAT data partition as the videos folder, so you can pop the
# SD card into a Windows PC and drag episodes straight onto it.
#
# FIRST: create the partition from Windows BEFORE the Pi's first boot —
# see "exFAT partition" in the README. Then run this ON the Pi:
#   bash setup_exfat.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VIDEOS="$DIR/videos"
DEV=/dev/mmcblk0

echo "==> Installing exFAT + partition tools..."
sudo apt update
sudo apt install -y exfatprogs cloud-guest-utils

# 1. Grow the OS root partition into the gap left before the exFAT
#    partition (first-boot auto-expand was blocked by the exFAT partition).
echo "==> Growing root partition into the reserved gap (if any)..."
if sudo growpart "$DEV" 2; then
  sudo resize2fs "${DEV}p2"
  echo "    root filesystem grown."
else
  echo "    no room to grow (already done) — fine."
fi

# 2. Find the exFAT partition — or a raw, unformatted data partition
#    (the prepare_card.ps1 first-boot route creates it unformatted)
PART=$(sudo blkid -t TYPE=exfat -o device | grep "^$DEV" | head -1)
if [ -z "$PART" ] && [ -b "${DEV}p3" ] && ! sudo blkid "${DEV}p3" >/dev/null 2>&1; then
  echo "==> Found unformatted data partition ${DEV}p3 — formatting as exFAT..."
  sudo mkfs.exfat -L PITV "${DEV}p3"
  PART="${DEV}p3"
fi
if [ -z "$PART" ]; then
  echo "!! No exFAT (or blank data) partition found on $DEV."
  echo "   Create it first — README: 'exFAT partition' (diskpart or prepare_card.ps1)."
  exit 1
fi
UUID=$(sudo blkid -s UUID -o value "$PART")
echo "==> Found exFAT partition $PART (UUID=$UUID)"

# 3. Preserve any videos already in the folder
mkdir -p "$VIDEOS"
TMP=""
if [ -n "$(ls -A "$VIDEOS" 2>/dev/null)" ]; then
  TMP=$(mktemp -d)
  echo "==> Stashing existing videos..."
  mv "$VIDEOS"/* "$TMP"/
fi

# 4. Mount it at the videos folder, permanently
if ! grep -q "UUID=$UUID" /etc/fstab; then
  echo "UUID=$UUID $VIDEOS exfat uid=$(id -u),gid=$(id -g),fmask=0113,dmask=0002,nofail,x-systemd.automount 0 0" \
    | sudo tee -a /etc/fstab >/dev/null
fi
sudo systemctl daemon-reload
sudo mount "$VIDEOS" 2>/dev/null || sudo mount -a

if [ -n "$TMP" ]; then
  echo "==> Restoring stashed videos onto the exFAT partition..."
  cp -r "$TMP"/* "$VIDEOS"/ && rm -rf "$TMP"
fi

df -h "$VIDEOS" | tail -1
echo
echo "Done. The videos folder now lives on the exFAT partition."
echo "Pop the SD card into Windows and it shows up as drive 'PITV'."
echo "Each folder you create on it becomes a channel."
