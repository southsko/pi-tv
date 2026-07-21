#!/bin/bash
# Boot-time diet for the TV. Run ON the Pi:  bash speedup_boot.sh
# Then: sudo reboot.  Diagnose leftovers with: systemd-analyze blame | head -15
set -e

BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

echo "==> Making sure no desktop fights the TV for the screen..."
if [ "$(systemctl get-default)" = "graphical.target" ]; then
  sudo systemctl set-default multi-user.target
fi
sudo systemctl disable lightdm 2>/dev/null || true

echo "==> Disabling services a TV does not need..."
# Kept on purpose: NetworkManager (WiFi), avahi (simpsonstv.local), ssh, smbd.
for svc in bluetooth hciuart ModemManager cups cups-browsed triggerhappy \
           NetworkManager-wait-online systemd-networkd-wait-online \
           raspi-config keyboard-setup; do
  sudo systemctl disable --now "$svc" 2>/dev/null && echo "    off: $svc" || true
done

echo "==> Disabling WiFi power-save (fixes laggy/dropping SSH on Zero W)..."
sudo tee /etc/NetworkManager/conf.d/wifi-powersave.conf >/dev/null <<EOF
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager 2>/dev/null || true

echo "==> Firmware boot tweaks (config.txt)..."
if ! grep -q "# pi-tv fastboot" "$BOOT/config.txt"; then
  sudo tee -a "$BOOT/config.txt" >/dev/null <<EOF

# pi-tv fastboot
disable_splash=1
boot_delay=0
dtoverlay=disable-bt
EOF
fi

echo "==> Quieting the console (cmdline.txt)..."
grep -q " quiet" "$BOOT/cmdline.txt" || sudo sed -i 's/$/ quiet loglevel=3 logo.nologo/' "$BOOT/cmdline.txt"

echo "==> Making the TV service start as early as possible..."
sudo sed -i 's/^After=.*/After=local-fs.target/' /etc/systemd/system/simpsonstv.service
sudo systemctl daemon-reload

echo
echo "Done. sudo reboot and time it."
echo "Still slow? Run: systemd-analyze blame | head -15  and investigate the top items."
