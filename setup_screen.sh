#!/bin/bash
# Configures the Waveshare 2.8" DPI capacitive touch LCD (the screen from
# the current Simpsons TV build guide) on Raspberry Pi OS Bookworm/Trixie.
#
#   bash setup_screen.sh        (reboot afterwards)
#
# Does what the Waveshare wiki says, scripted:
#  * installs the display overlays (DTBO files) into the boot partition
#  * appends the display + touch + PWM-audio config to config.txt
#  * sets portrait rotation via cmdline.txt (video=DPI-1:...rotate=90)
#
# Pi Zero 2 W green-tint fix (grey pixels look green): run again with
#   ZERO_FIX=1 bash setup_screen.sh
set -e

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot
MARK="# --- pi-tv waveshare 2.8 dpi ---"
ROT="${ROTATE:-270}"   # framebuffer rotation; override with ROTATE=90 etc.

echo "==> Installing tools..."
sudo apt update
sudo apt install -y wget unzip

echo "==> Downloading Waveshare 2.8\" DPI overlays..."
wget -q -O /tmp/28dpi.zip "https://files.waveshare.com/wiki/2.8inc-DPI-LCD/28DPI-DTBO.zip"
rm -rf /tmp/28dpi && mkdir -p /tmp/28dpi
unzip -o -q /tmp/28dpi.zip -d /tmp/28dpi
find /tmp/28dpi -name "*.dtbo" -exec sudo cp {} "$BOOT/overlays/" \;
echo "    overlays installed to $BOOT/overlays/"

if [ -n "$ZERO_FIX" ]; then
  echo "==> Applying Pi Zero 2 W green-tint fix..."
  wget -q -O /tmp/vc4-kms-DPI-28inch.dtbo \
    "https://files.waveshare.com/wiki/2.8inch%20DPI%20LCD/zero%20dtbo/vc4-kms-DPI-28inch.dtbo"
  sudo cp /tmp/vc4-kms-DPI-28inch.dtbo "$BOOT/overlays/vc4-kms-dpi-2inch8.dtbo"
fi

if ! grep -q "$MARK" "$BOOT/config.txt"; then
  echo "==> Adding screen + audio config to config.txt..."
  sudo tee -a "$BOOT/config.txt" >/dev/null <<EOF

$MARK
dtoverlay=vc4-kms-v3d
dtoverlay=waveshare-28dpi-3b-4b
dtoverlay=waveshare-28dpi-3b
dtoverlay=waveshare-28dpi-4b
dtoverlay=waveshare-touch-28dpi
dtoverlay=vc4-kms-dpi-2inch8
dtparam=audio=on
dtoverlay=audremap,enable_jack,pins_18_19
# keep backlight off during boot; the TV service turns it on when ready
gpio=18=op,dl
# --- end pi-tv ---
EOF
else
  echo "==> config.txt already configured, skipping"
fi

if ! grep -q 'hw:Headphones' /etc/asound.conf 2>/dev/null; then
  echo "==> Pointing ALSA default output at the PWM audio (Headphones card)..."
  sudo tee /etc/asound.conf >/dev/null <<'ALSAEOF'
pcm.!default {
  type plug
  slave.pcm "hw:Headphones"
}
ctl.!default {
  type hw
  card Headphones
}
ALSAEOF
fi

if grep -qE 'video=DPI-1:[^ ]*rotate=[0-9]+' "$BOOT/cmdline.txt"; then
  echo "==> Updating framebuffer rotation in cmdline.txt (rotate=$ROT)..."
  sudo sed -i -E "s/(video=DPI-1:[^ ]*rotate=)[0-9]+/\1$ROT/" "$BOOT/cmdline.txt"
else
  echo "==> Setting portrait rotation in cmdline.txt (rotate=$ROT)..."
  sudo sed -i "1s|^|video=DPI-1:480x640M@60,rotate=$ROT |" "$BOOT/cmdline.txt"
fi

echo
echo "Done. Reboot to bring the screen up:  sudo reboot"
