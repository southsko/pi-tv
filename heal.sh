#!/bin/bash
# Power-loss self-heal. Wired as the service's ExecStartPre, so it runs before
# the TV starts on every boot. If an unclean shutdown zeroes or corrupts a
# source file, this restores it from the golden copy this script lives in.
# Always exits 0 so a heal hiccup can never block startup.
#
# Lives in <app>-golden/ ; the live app is the same path without "-golden".
GOLDEN="$(cd "$(dirname "$0")" && pwd)"
APP="${GOLDEN%-golden}"
restored=0

for f in tv.py channels.py hardware.py mpv_ipc.py webui.py touch.py \
         pitv_config.py pitv_lib.sh configure.sh tvctl.sh; do
  [ -f "$GOLDEN/$f" ] || continue
  bad=0
  [ -s "$APP/$f" ] || bad=1
  case "$f" in
    *.py) python3 -m py_compile "$APP/$f" 2>/dev/null || bad=1 ;;
    *.sh) bash -n "$APP/$f" 2>/dev/null || bad=1 ;;
  esac
  if [ "$bad" = 1 ]; then
    echo "[heal] $f missing/zero/corrupt -> restoring from golden"
    cp -a "$GOLDEN/$f" "$APP/$f" && restored=1
  fi
done

if [ -f "$GOLDEN/static.mp4" ] && [ ! -s "$APP/static.mp4" ]; then
  echo "[heal] static.mp4 missing/zero -> restoring"
  cp -a "$GOLDEN/static.mp4" "$APP/static.mp4" && restored=1
fi

if [ -f "$GOLDEN/config.json" ]; then
  if [ ! -s "$APP/config.json" ] || ! python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$APP/config.json" 2>/dev/null; then
    echo "[heal] config.json missing/corrupt -> restoring"
    cp -a "$GOLDEN/config.json" "$APP/config.json" && restored=1
  fi
fi

[ "$restored" = 1 ] && sync
echo "[heal] check complete (restored=$restored)"
exit 0
