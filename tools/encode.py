#!/usr/bin/env python3
"""Batch-encode videos for Pi TV.

Run this ON YOUR PC (never the Pi Zero — it would take hours). Drop it in a
folder full of source videos and run:

    python3 encode.py

Every video in this folder (and subfolders) is re-encoded into ./encoded/ as
H.264 baseline 480p with stereo AAC audio — the format the Pi's hardware
decoder (v4l2m2m) plays smoothly. Copy the results into your channel folders
(videos/<channel>/) or straight onto the PITV card.

Options (env vars):
    HEIGHT=480     output height in pixels (width auto, keeps aspect)
    CRF=23         quality; lower = better/bigger (18–28 sensible)
    PRESET=fast    x264 speed/size tradeoff
"""
import os
import subprocess
import sys

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm", ".flv", ".wmv")

HEIGHT = os.environ.get("HEIGHT", "480")
CRF = os.environ.get("CRF", "23")
PRESET = os.environ.get("PRESET", "fast")


def is_video(name):
    return name.lower().endswith(VIDEO_EXTS) and not name.startswith(".")


def main():
    directory = os.path.dirname(os.path.realpath(__file__))
    dest = os.path.join(directory, "encoded")
    os.makedirs(dest, exist_ok=True)

    sources = [
        os.path.join(dp, f)
        for dp, dn, files in os.walk(directory)
        for f in files
        if is_video(f) and os.path.realpath(dp) != os.path.realpath(dest)
    ]

    if not sources:
        print("No videos found next to this script.")
        return

    print("Found %d file(s). Encoding to %s\n" % (len(sources), dest))
    ok, failed, skipped = 0, 0, 0

    for src in sorted(sources):
        name = os.path.splitext(os.path.basename(src))[0] + ".mp4"
        out = os.path.join(dest, name)
        if os.path.isfile(out):
            print("skip (exists): %s" % name)
            skipped += 1
            continue

        print("Encoding: %s" % name)
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", "scale=-2:%s" % HEIGHT,
            "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
            "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart",
            out,
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
            # leave no half-written file behind
            if os.path.isfile(out):
                os.remove(out)
            print("  FAILED: %s" % name)
            tail = result.stderr.decode("utf-8", "replace").strip().splitlines()
            for line in tail[-3:]:
                print("    %s" % line)

    print("\nDone. %d encoded, %d skipped, %d failed." % (ok, skipped, failed))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
