#!/bin/bash
# Root helper that lets the Simpsons TV web UI manage Samba share auth.
#
# Installed by setup_share.sh to /usr/local/sbin/pitv-share-auth (root-owned,
# 0755) and granted a scoped NOPASSWD sudoers rule, so the web UI (running as
# the pi-tv user) can flip the [videos] share between guest access and a
# username/password login without handing the web UI blanket root.
#
# Keeping the privileged logic in one small root-owned script — instead of
# NOPASSWD on raw useradd/smbpasswd/tee — keeps the attack surface auditable.
#
# Usage (run via: sudo -n /usr/local/sbin/pitv-share-auth <cmd>):
#   status          print "mode=open|locked" and "user=<name>"
#   open            make [videos] guest-accessible (no login)
#   lock <user>     require <user> + password (password read from STDIN),
#                   creating the Linux user if it doesn't exist
#
# The password is only ever read from stdin, never from argv, so it can't leak
# via the process list. The username is validated here regardless of caller.
set -euo pipefail

CONF=/etc/samba/smb.conf
SHARE=videos

die() { echo "error: $*" >&2; exit 1; }

[ -f "$CONF" ] || die "smb.conf not found — is Samba installed?"

# Pull "path =" from the existing [videos] block (fall back to a sane default).
share_path() {
  awk -v s="[$SHARE]" '
    $0==s {inb=1; next}
    /^\[/ {inb=0}
    inb && tolower($0) ~ /^[[:space:]]*path[[:space:]]*=/ {
      sub(/^[^=]*=[[:space:]]*/, ""); print; exit }
  ' "$CONF"
}

# Rewrite the [videos] block. $1 = guest (yes|no), $2 = user.
write_block() {
  local guest=$1 user=$2 path tmp
  path=$(share_path); [ -n "$path" ] || path="/home/$user/pi-tv/videos"
  tmp=$(mktemp)
  # Everything except the old [videos] block...
  awk -v s="[$SHARE]" '
    $0==s {inb=1; next}
    /^\[/ {inb=0}
    !inb {print}
  ' "$CONF" > "$tmp"
  # ...trim trailing blank lines, then append a fresh block.
  sed -i -e :a -e '/^\n*$/{$d;N;ba}' "$tmp"
  {
    printf '\n[%s]\n' "$SHARE"
    printf '   path = %s\n' "$path"
    printf '   browseable = yes\n'
    printf '   writeable = yes\n'
    if [ "$guest" = yes ]; then
      printf '   guest ok = yes\n'
    else
      printf '   guest ok = no\n'
      printf '   valid users = %s\n' "$user"
    fi
    printf '   force user = %s\n' "$user"
    printf '   create mask = 0664\n'
    printf '   directory mask = 0775\n'
  } >> "$tmp"
  # Validate before touching the live config; keep a one-time backup.
  testparm -s "$tmp" >/dev/null 2>&1 || { rm -f "$tmp"; die "smb.conf validation failed"; }
  [ -f "$CONF.pitv.bak" ] || cp -a "$CONF" "$CONF.pitv.bak"
  install -o root -g root -m 0644 "$tmp" "$CONF"
  rm -f "$tmp"
}

valid_username() {
  [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || return 1
  case "$1" in
    root|daemon|bin|sys|sync|games|man|lp|mail|news|uucp|proxy|www-data|\
    backup|list|irc|nobody|systemd*|messagebus|sshd) return 1 ;;
  esac
  return 0
}

cmd=${1:-status}
case "$cmd" in
  status)
    if awk -v s="[$SHARE]" '
          $0==s {i=1; next} /^\[/ {i=0}
          i && tolower($0) ~ /guest ok[[:space:]]*=[[:space:]]*yes/ {f=1}
          END {exit !f}' "$CONF"; then
      echo "mode=open"
    else
      echo "mode=locked"
    fi
    echo "user=$(awk -v s="[$SHARE]" '
      $0==s {i=1; next} /^\[/ {i=0}
      i && tolower($0) ~ /^[[:space:]]*valid users[[:space:]]*=/ {
        sub(/^[^=]*=[[:space:]]*/, ""); print; exit }' "$CONF")"
    ;;

  open)
    # Guest writes are owned by whoever invoked us (the pi-tv user).
    write_block yes "${SUDO_USER:-root}"
    systemctl restart smbd
    echo ok
    ;;

  lock)
    user=${2:-}
    valid_username "$user" || die "invalid username"
    IFS= read -r pass || true      # password from stdin, first line
    [ -n "$pass" ] || die "empty password"
    if id "$user" >/dev/null 2>&1; then
      [ "$(id -u "$user")" -ge 1000 ] || die "refusing to use a system account"
    else
      useradd -M -s /usr/sbin/nologin "$user"
    fi
    printf '%s\n%s\n' "$pass" "$pass" | smbpasswd -a -s "$user" >/dev/null
    smbpasswd -e "$user" >/dev/null 2>&1 || true
    write_block no "$user"
    systemctl restart smbd
    echo ok
    ;;

  *)
    die "unknown command: $cmd"
    ;;
esac
