#!/bin/bash
# Generates a 1.5-second analog TV static clip (static.mp4) with white noise
# audio, used as the channel-change effect. Requires ffmpeg.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ffmpeg -y \
  -f lavfi -i "nullsrc=s=640x480:d=1.5,geq=random(1)*255:128:128" \
  -f lavfi -i "anoisesrc=d=1.5:c=white:a=0.4" \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p \
  -c:a aac -shortest \
  "$DIR/static.mp4"
echo "Wrote $DIR/static.mp4"
