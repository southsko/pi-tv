#!/usr/bin/env python3
"""Batch-encode videos for Pi TV.

Run this ON YOUR PC (never the Pi Zero — it would take hours). Drop it in a
folder full of source videos and run:

    python3 encode.py

Every video in this folder AND all subfolders is re-encoded into ./encoded/,
mirroring the folder structure — so Season 1/, Season 2/, ... come out as
matching subfolders you can drop straight into videos/ as channels. Output is
H.264 baseline 480p with stereo AAC audio — the format the Pi's hardware
decoder (v4l2m2m) plays smoothly.

Anything with "sample" in the file or folder name is skipped.

Options (env vars):
    HEIGHT=480     output height in pixels (width auto, keeps aspect)
    CRF=23         quality; lower = better/bigger (18–28 sensible)
    PRESET=fast    x264 speed/size tradeoff
    SKIP=sample    comma-separated words to ignore (default: sample)
"""
import os
import subprocess
import sys

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm", ".flv", ".wmv")

HEIGHT = os.environ.get("HEIGHT", "480")
CRF = os.environ.get("CRF", "23")
PRESET = os.environ.get("PRESET", "fast")
SKIP_WORDS = [w.strip().lower() for w in
              os.environ.get("SKIP", "sample").split(",") if w.strip()]


def is_video(name):
    return name.lower().endswith(VIDEO_EXTS) and not name.startswith(".")


def is_ignored(relpath):
    low = relpath.lower()
    return any(w in low for w in SKIP_WORDS)


def main():
    directory = os.path.dirname(os.path.realpath(__file__))
    dest = os.path.join(directory, "encoded")
    os.makedirs(dest, exist_ok=True)

    sources = []
    for dp, dn, files in os.walk(directory):
        if os.path.realpath(dp) == os.path.realpath(dest):
            dn[:] = []            # don't descend into our own output
            continue
        # prune ignored subfolders (e.g. "Sample") so we skip their contents
        dn[:] = [d for d in dn if not is_ignored(d)]
        for f in files:
            if is_video(f) and not is_ignored(f):
                sources.append(os.path.join(dp, f))

    if not sources:
        print("No videos found next to this script.")
        return

    print("Found %d file(s). Encoding to %s (mirroring folders)\n"
          % (len(sources), dest))
    ok, failed, skipped = 0, 0, 0

    for src in sorted(sources):
        # mirror the source's relative folder path into encoded/
        rel = os.path.relpath(src, directory)
        rel_out = os.path.splitext(rel)[0] + ".mp4"
        out = os.path.join(dest, rel_out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.isfile(out):
            print("skip (exists): %s" % rel_out)
            skipped += 1
            continue

        print("Encoding: %s" % rel_out)
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
