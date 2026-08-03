#!/bin/bash
# Shared helpers for configure.sh and tvctl. Source it:
#   source "$(dirname "$0")/pitv_lib.sh"
# PITV_DIR may be pre-set (tvctl launcher does this); otherwise it's inferred
# from this file's location.

PITV_DIR="${PITV_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
CONFIG="$PITV_DIR/config.json"
GOLDEN="${PITV_DIR}-golden"
SERVICE=simpsonstv
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

# ---- config.json (via pitv_config.py, always valid JSON) --------------------
cfg() { PITV_CONFIG="$CONFIG" python3 "$PITV_DIR/pitv_config.py" "$@"; }
cfg_get() { cfg get "$1"; }

# ---- golden copy (power-loss self-heal source) ------------------------------
golden_refresh_config() { [ -d "$GOLDEN" ] && cp -a "$CONFIG" "$GOLDEN/config.json" 2>/dev/null; }
golden_refresh_all() {
  [ -d "$GOLDEN" ] || return 0
  cp -a "$PITV_DIR"/*.py "$GOLDEN"/ 2>/dev/null
  [ -f "$PITV_DIR/static.mp4" ] && cp -a "$PITV_DIR/static.mp4" "$GOLDEN"/ 2>/dev/null
  cp -a "$CONFIG" "$GOLDEN/config.json" 2>/dev/null
  [ -f "$PITV_DIR/heal.sh" ] && cp -a "$PITV_DIR/heal.sh" "$GOLDEN"/ 2>/dev/null
  sync
}

# ---- rotation: set video (config.json) + framebuffer (cmdline.txt) together -
cmdline_rotate() {  # $1 = degrees
  local deg="$1" cl="$BOOT/cmdline.txt"
  [ -f "$cl" ] || return 0
  if grep -qE 'video=DPI-1:[^ ]*rotate=[0-9]+' "$cl"; then
    sudo sed -i -E "s/(video=DPI-1:[^ ]*rotate=)[0-9]+/\1$deg/" "$cl"
  elif grep -qE 'video=DPI-1:[^ ]+' "$cl"; then
    sudo sed -i -E "s/(video=DPI-1:[0-9]+x[0-9]+[^ ,]*)/\1,rotate=$deg/" "$cl"
  else
    sudo sed -i "1s|^|video=DPI-1:480x640M@60,rotate=$deg |" "$cl"
  fi
}

set_rotation() {  # $1 = degrees; returns 0. Framebuffer change needs a reboot.
  local deg="$1"
  cfg rotate "$deg" || return 1
  cmdline_rotate "$deg"
  golden_refresh_config
}

# ---- simple scalar setters --------------------------------------------------
set_web_port()  { cfg set web_port "$1" --int && golden_refresh_config; }
set_volume()    { cfg set static_volume "$1" --int && golden_refresh_config; }
set_power_mode(){ cfg set power_switch_mode "$1" && golden_refresh_config; }

# ---- samba ------------------------------------------------------------------
# smbd lives in /usr/sbin which isn't on a non-login PATH, so detect via dpkg.
samba_present() { dpkg -s samba >/dev/null 2>&1 || [ -x /usr/sbin/smbd ]; }
samba_share_defined() { grep -q '^\[videos\]' /etc/samba/smb.conf 2>/dev/null; }
samba_on() { systemctl is-active --quiet smbd; }  # is the share running now?
samba_enable() {
  if samba_present && samba_share_defined; then
    sudo systemctl enable --now smbd
  else
    bash "$PITV_DIR/setup_share.sh"
  fi
}
samba_disable() { sudo systemctl disable --now smbd 2>/dev/null || true; }

# Root-owned auth helper installed by setup_share.sh. Reads (status) need no
# privileges; writes (lock/open) go through the scoped NOPASSWD sudoers rule.
SHARE_AUTH="/usr/local/sbin/pitv-share-auth"
samba_auth_ready() { [ -x "$SHARE_AUTH" ]; }
samba_mode() { samba_auth_ready && "$SHARE_AUTH" status 2>/dev/null | sed -n 's/^mode=//p'; }
samba_user() { samba_auth_ready && "$SHARE_AUTH" status 2>/dev/null | sed -n 's/^user=//p'; }
samba_open() {  # make the share guest-accessible (no login)
  samba_auth_ready || { echo "run setup_share.sh on the TV first" >&2; return 1; }
  sudo -n "$SHARE_AUTH" open
}
samba_lock() {  # require login as user $1; password read from stdin
  samba_auth_ready || { echo "run setup_share.sh on the TV first" >&2; return 1; }
  sudo -n "$SHARE_AUTH" lock "$1"
}

# ---- service ----------------------------------------------------------------
tv_restart() { sudo systemctl restart "$SERVICE"; }
tv_start()   { sudo systemctl start "$SERVICE"; }
tv_stop()    { sudo systemctl stop "$SERVICE"; }
tv_active()  { systemctl is-active --quiet "$SERVICE"; }

# ---- misc -------------------------------------------------------------------
this_ip()   { hostname -I 2>/dev/null | awk '{print $1}'; }
this_host() { hostname; }
have_whiptail() { command -v whiptail >/dev/null 2>&1 && [ -t 0 ] && [ -t 1 ]; }
