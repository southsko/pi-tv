#!/bin/bash
# tvctl - one-liner control for Pi TV, so you never hand-edit files.
# Installed to /usr/local/bin/tvctl by install.sh (a launcher that sets
# PITV_DIR and execs this). Also runnable directly: bash tvctl.sh <cmd>
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PITV_DIR="${PITV_DIR:-$HERE}"
# shellcheck source=/dev/null
source "$PITV_DIR/pitv_lib.sh"

usage() {
  cat <<EOF
tvctl - control the Pi TV

  tvctl status              service state + current settings + URLs
  tvctl start|stop|restart  control the TV service
  tvctl logs                follow the log (Ctrl-C to stop)
  tvctl config              print config.json
  tvctl reconfigure         open the full menu (whiptail)

  tvctl rotate <0|90|180|270>   set display rotation (reboot for framebuffer)
  tvctl volume <0-100>          channel-change static loudness
  tvctl port <n>                web remote port
  tvctl power <toggle|switch>   power button behaviour
  tvctl set <dotted.key> <val> [--int|--float|--bool|--json]

  tvctl samba <on|off|status>   network share of the videos folder
  tvctl samba login <user>      require a username+password (prompts for pw)
  tvctl samba open              drop the login, back to open guest access
  tvctl golden                  refresh the self-heal golden copy from live files
  tvctl heal                    run the self-heal check now
  tvctl update                  git pull, refresh golden, restart

Settings that affect playback restart the TV automatically.
EOF
}

need_restart_and_go() { golden_refresh_config; tv_active && tv_restart; }

case "${1:-}" in
  status)
    echo "service : $(systemctl is-active "$SERVICE") ($(systemctl is-enabled "$SERVICE" 2>/dev/null))"
    echo "rotation: $(cfg_get osd_rotate)deg   volume: $(cfg_get static_volume)   power: $(cfg_get power_switch_mode)"
    echo "web     : http://$(this_host).local:$(cfg_get web_port)  (or http://$(this_ip):$(cfg_get web_port))"
    if samba_on; then
      case "$(samba_mode)" in
        locked) echo "samba   : ON   \\\\$(this_host)\\videos  (login: $(samba_user))" ;;
        *)      echo "samba   : ON   \\\\$(this_host)\\videos  (open)" ;;
      esac
    else echo "samba   : off"; fi
    ;;
  start)   tv_start ;;
  stop)    tv_stop ;;
  restart) tv_restart ;;
  logs)    journalctl -u "$SERVICE" -f ;;
  config)  cfg show ;;
  reconfigure|menu) PITV_DIR="$PITV_DIR" bash "$PITV_DIR/configure.sh" ;;

  rotate)  set_rotation "$2"  && { echo "rotation -> $2deg (reboot to update the framebuffer)"; need_restart_and_go; } ;;
  volume)  set_volume "$2"    && { echo "volume -> $2"; need_restart_and_go; } ;;
  port)    set_web_port "$2"  && { echo "web port -> $2"; need_restart_and_go; } ;;
  power)   set_power_mode "$2" && { echo "power mode -> $2"; need_restart_and_go; } ;;
  set)     shift; cfg set "$@" && need_restart_and_go && echo "set ok" ;;

  samba)
    case "$2" in
      on)     samba_enable; samba_on && echo "samba ON: \\\\$(this_host)\\videos" ;;
      off)    samba_disable; echo "samba off" ;;
      open)   samba_open && echo "share is now open (no login)" ;;
      login)
        u="$3"; [ -n "$u" ] || { echo "usage: tvctl samba login <user>"; exit 1; }
        printf 'Samba password for %s: ' "$u" >&2; read -rs pw; echo >&2
        [ -n "$pw" ] || { echo "no password given"; exit 1; }
        printf '%s\n' "$pw" | samba_lock "$u" \
          && echo "login set: '\\\\$(this_host)\\videos' now requires user '$u'" ;;
      status|"")
        if samba_on; then
          case "$(samba_mode)" in
            locked) echo "on (login required, user: $(samba_user))" ;;
            open)   echo "on (open, no login)" ;;
            *)      echo "on" ;;
          esac
        else echo "off"; fi ;;
      *) echo "usage: tvctl samba <on|off|open|login <user>|status>"; exit 1 ;;
    esac
    ;;

  golden)  golden_refresh_all && echo "golden copy refreshed from live files" ;;
  heal)    [ -x "$GOLDEN/heal.sh" ] && bash "$GOLDEN/heal.sh" || echo "no golden/heal.sh at $GOLDEN" ;;
  update)
    ( cd "$PITV_DIR" && git pull ) && golden_refresh_all && tv_restart && echo "updated + restarted"
    ;;

  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; echo; usage; exit 1 ;;
esac
