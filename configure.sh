#!/bin/bash
# Smart, menu-driven setup / reconfigure for Pi TV. Uses whiptail (ships with
# Raspberry Pi OS). Run it directly (bash configure.sh) or via: tvctl reconfigure
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PITV_DIR="${PITV_DIR:-$HERE}"
# shellcheck source=/dev/null
source "$PITV_DIR/pitv_lib.sh"

TITLE="Pi TV setup"
CHANGED=0
NEED_REBOOT=0

if ! have_whiptail; then
  echo "This configurator needs an interactive terminal (whiptail)."
  echo "For scripted changes use tvctl, e.g.:  tvctl rotate 90 | tvctl samba off"
  exit 1
fi

info() { whiptail --title "$TITLE" --msgbox "$1" "${2:-12}" 70; }

# run a heavy, chatty command (apt etc.) outside the whiptail canvas
run_plain() {
  clear
  "$@"
  echo
  read -r -p "Press Enter to return to the menu... " _
}

menu_rotation() {
  local cur; cur=$(cfg_get osd_rotate); [ -n "$cur" ] || cur=270
  local d
  d=$(whiptail --title "Display rotation" --radiolist \
    "How is the screen oriented? Sets video, touch and framebuffer together.\nThe framebuffer part takes effect after a reboot." \
    16 70 4 \
    0   "0   - no rotation"              "$([ "$cur" = 0 ]   && echo ON || echo OFF)" \
    90  "90  - rotated right"            "$([ "$cur" = 90 ]  && echo ON || echo OFF)" \
    180 "180 - upside down"              "$([ "$cur" = 180 ] && echo ON || echo OFF)" \
    270 "270 - rotated left (default)"   "$([ "$cur" = 270 ] && echo ON || echo OFF)" \
    3>&1 1>&2 2>&3) || return
  [ -n "$d" ] || return
  set_rotation "$d" && { CHANGED=1; NEED_REBOOT=1; }
}

menu_port() {
  local cur; cur=$(cfg_get web_port); [ -n "$cur" ] || cur=8080
  local v
  v=$(whiptail --title "Web remote port" --inputbox "Port for the phone web remote:" 10 60 "$cur" 3>&1 1>&2 2>&3) || return
  if [[ "$v" =~ ^[0-9]+$ ]] && [ "$v" -ge 1 ] && [ "$v" -le 65535 ]; then
    set_web_port "$v"; CHANGED=1
  else
    info "Not a valid port number."
  fi
}

menu_volume() {
  local cur; cur=$(cfg_get static_volume); [ -n "$cur" ] || cur=40
  local v
  v=$(whiptail --title "Static volume" --inputbox "Channel-change static loudness (0-100):" 10 60 "$cur" 3>&1 1>&2 2>&3) || return
  if [[ "$v" =~ ^[0-9]+$ ]] && [ "$v" -le 100 ]; then
    set_volume "$v"; CHANGED=1
  else
    info "Enter a number from 0 to 100."
  fi
}

menu_power() {
  local cur; cur=$(cfg_get power_switch_mode); [ -n "$cur" ] || cur=toggle
  local m
  m=$(whiptail --title "Power switch mode" --radiolist "How the power button behaves:" 12 66 2 \
    toggle "press = on/off toggle"          "$([ "$cur" = toggle ] && echo ON || echo OFF)" \
    switch "switch = follows level (on/off)" "$([ "$cur" = switch ] && echo ON || echo OFF)" \
    3>&1 1>&2 2>&3) || return
  [ -n "$m" ] && { set_power_mode "$m"; CHANGED=1; }
}

menu_samba() {
  if samba_on; then
    whiptail --title "Samba share" --yesno "Samba share is ON:\n  \\\\$(this_host)\\videos\n\nTurn it OFF?" 12 66 \
      && { samba_disable; info "Samba share disabled."; }
  else
    if whiptail --title "Samba share" --yesno "Samba share is OFF.\n\nTurn it ON? (installs Samba the first time)" 11 66; then
      if samba_present && samba_share_defined; then samba_enable; else run_plain samba_enable; fi
      samba_on && info "Samba share enabled:\n  \\\\$(this_host)\\videos"
    fi
  fi
}

menu_screen() {
  whiptail --title "Waveshare screen" --yesno \
    "(Re)install the Waveshare 2.8\" DPI screen + audio config?\nSafe to run again. Needs a reboot afterward." 11 68 || return
  local rot; rot=$(cfg_get osd_rotate); [ -n "$rot" ] || rot=270
  run_plain env ROTATE="$rot" bash "$PITV_DIR/setup_screen.sh"
  NEED_REBOOT=1
}

menu_exfat() {
  whiptail --title "exFAT video partition" --yesno \
    "Mount an exFAT data partition as the videos folder?\nOnly if the card was partitioned for it (see README).\n\nProceed?" 12 68 || return
  run_plain bash "$PITV_DIR/setup_exfat.sh"
}

while true; do
  ROT=$(cfg_get osd_rotate); PORT=$(cfg_get web_port)
  VOL=$(cfg_get static_volume); PWR=$(cfg_get power_switch_mode)
  if samba_on; then SAMBA="ON"; else SAMBA="off"; fi
  choice=$(whiptail --title "$TITLE" --menu \
    "Choose what to change. Values in [] are current." 21 74 11 \
    rotate "Display rotation .............. [${ROT}deg]" \
    port   "Web remote port ............... [${PORT}]" \
    volume "Static (channel-change) volume  [${VOL}]" \
    power  "Power switch mode ............. [${PWR}]" \
    samba  "Samba network share ........... [${SAMBA}]" \
    screen "(Re)configure Waveshare screen" \
    exfat  "Mount exFAT video partition" \
    apply  "Apply changes & restart the TV" \
    quit   "Exit" \
    3>&1 1>&2 2>&3) || break

  case "$choice" in
    rotate) menu_rotation ;;
    port)   menu_port ;;
    volume) menu_volume ;;
    power)  menu_power ;;
    samba)  menu_samba ;;
    screen) menu_screen ;;
    exfat)  menu_exfat ;;
    apply)  tv_restart && { CHANGED=0; info "TV restarted."; } ;;
    quit)   break ;;
  esac
done

golden_refresh_config
[ "$CHANGED" = 1 ] && tv_active && tv_restart 2>/dev/null

clear
PORT=$(cfg_get web_port)
echo "Web remote:  http://$(this_host).local:$PORT   (or http://$(this_ip):$PORT)"
samba_on && echo "File share:  \\\\$(this_host)\\videos"
echo "Control it:  tvctl status | tvctl reconfigure | tvctl samba on/off"
if [ "$NEED_REBOOT" = 1 ]; then
  echo
  echo ">>> A rotation/screen change needs a reboot to take full effect:  sudo reboot"
fi
