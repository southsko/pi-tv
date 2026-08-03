#!/bin/sh
# Login MOTD for the Simpsons TV appliance. install.sh copies this to
# /etc/update-motd.d/99-pitv, rewriting /home/pi/simpsonstv to the real path.
# Runs at each login, so IP, web port and Samba state are resolved live.
HN=$(hostname)
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$IP" ] && IP="(no IP yet - check network)"

DIR=/home/pi/simpsonstv
PORT=$(PITV_CONFIG="$DIR/config.json" python3 "$DIR/pitv_config.py" get web_port 2>/dev/null)
[ -n "$PORT" ] || PORT=80
if [ "$PORT" = 80 ]; then
  WEB_HN="http://$HN.local";        WEB_IP="http://$IP"
else
  WEB_HN="http://$HN.local:$PORT";  WEB_IP="http://$IP:$PORT"
fi

cat <<'EOF'

  Simpsons TV  --  power-loss-hardened appliance
  ==================================================================
  ACCESS
EOF
printf '    Web remote : %s   (or %s)\n' "$WEB_HN" "$WEB_IP"
if systemctl is-active --quiet smbd; then
  printf '    File share : \\\\%s.local\\videos       (or \\\\%s\\videos)\n' "$HN" "$IP"
  echo   '                 (Samba: guest, read/write; or use the web remote)'
else
  echo   '    File share : Samba off   (enable with:  tvctl samba on)'
fi
cat <<'EOF'
  ------------------------------------------------------------------
  Change anything without editing files:
      tvctl status | tvctl reconfigure | tvctl rotate 90
      tvctl volume 60 | tvctl port 80 | tvctl samba on|off

  This unit gets unplugged with no clean shutdown, so it self-heals:
  the TV service restores app source from  /home/pi/simpsonstv-golden/
  on every boot if a file is missing / zero-length / won't compile.

  >> IF YOU EDIT APP FILES BY HAND, refresh the golden copy after:
       tvctl golden

  * Logs are volatile (in RAM): 'journalctl' shows this boot only.
  * DO NOT enable overlayfs -- it hangs boot on this Waveshare DPI
    board. Recovery: pull the SD card, and on another PC remove
    'overlayroot=tmpfs' from bootfs/cmdline.txt and set
    '#auto_initramfs=1' in bootfs/config.txt (plain ASCII, no BOM).
  * Full details: README.md  ->  "Modifying this unit"
  ==================================================================
EOF
