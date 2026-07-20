#!/bin/bash
# Sets up a Samba network share of the videos folder, so the TV shows up
# as a network drive: \\simpsonstv\videos (Windows) or smb://simpsonstv.local
# on Mac. Drag episodes in, hit Rescan in the web UI (or just change channel).
#
# Run ON the Pi:  bash setup_share.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VIDEOS="$DIR/videos"
mkdir -p "$VIDEOS"

echo "==> Installing Samba..."
sudo apt update
sudo apt install -y samba

echo "==> Adding [videos] share to /etc/samba/smb.conf..."
if ! grep -q "^\[videos\]" /etc/samba/smb.conf; then
  sudo tee -a /etc/samba/smb.conf >/dev/null <<EOF

[videos]
   path = $VIDEOS
   browseable = yes
   writeable = yes
   guest ok = yes
   force user = $USER
   create mask = 0664
   directory mask = 0775
EOF
else
  echo "    [videos] share already present, leaving it alone."
fi

sudo systemctl restart smbd

echo "==> Allowing the web UI to toggle the share (sudoers rule)..."
sudo tee /etc/sudoers.d/simpsonstv-samba >/dev/null <<EOF
$USER ALL=(root) NOPASSWD: /usr/bin/systemctl start smbd, /usr/bin/systemctl stop smbd, /usr/bin/systemctl enable smbd, /usr/bin/systemctl disable smbd
EOF
sudo chmod 440 /etc/sudoers.d/simpsonstv-samba

echo
echo "Done. On Windows open:  \\\\$(hostname)\\videos"
echo "On Mac/Linux:           smb://$(hostname).local/videos"
echo
echo "Note: the share allows guest write access — fine for a home LAN,"
echo "not for anything else. Each subfolder you create becomes a channel."
