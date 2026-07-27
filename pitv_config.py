#!/usr/bin/env python3
"""config.json helper for the installer and `tvctl` — keeps config.json valid
JSON so nothing has to hand-edit it. All writes are atomic (temp + os.replace).

Usage:
  pitv_config.py [--config PATH] get <dotted.key>
  pitv_config.py [--config PATH] set <dotted.key> <value> [--int|--float|--bool|--json]
  pitv_config.py [--config PATH] rotate <0|90|180|270>
  pitv_config.py [--config PATH] show

`rotate` is the important one: display rotation lives in three places that must
agree — osd_rotate, touch.rotate, and the mpv --video-rotate flag — so it sets
all three at once. (The framebuffer rotate in cmdline.txt is handled in bash.)
"""
import json
import os
import sys

VALID_ROT = (0, 90, 180, 270)


def load(p):
    with open(p) as f:
        return json.load(f)


def save(p, cfg):
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, p)


def get(cfg, dotted):
    cur = cfg
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def set_(cfg, dotted, value):
    keys = dotted.split(".")
    cur = cfg
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def set_rotation(cfg, deg):
    cfg["osd_rotate"] = deg
    cfg.setdefault("touch", {})["rotate"] = deg
    mpv = [a for a in cfg.get("mpv_args", []) if not a.startswith("--video-rotate")]
    mpv.append("--video-rotate=%d" % deg)
    cfg["mpv_args"] = mpv


def main():
    args = sys.argv[1:]
    path = os.environ.get("PITV_CONFIG")
    if args and args[0] == "--config":
        path, args = args[1], args[2:]
    if not path:
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")

    cmd = args[0] if args else ""

    if cmd == "get":
        val = get(load(path), args[1])
        if val is None:
            print("")
        elif isinstance(val, (dict, list)):
            print(json.dumps(val))
        elif isinstance(val, bool):
            print("true" if val else "false")
        else:
            print(val)

    elif cmd == "set":
        cfg = load(path)
        key, raw, rest = args[1], args[2], args[3:]
        if "--int" in rest:
            val = int(raw)
        elif "--float" in rest:
            val = float(raw)
        elif "--bool" in rest:
            val = raw.lower() in ("1", "true", "yes", "on")
        elif "--json" in rest:
            val = json.loads(raw)
        else:
            val = raw
        set_(cfg, key, val)
        save(path, cfg)

    elif cmd == "rotate":
        deg = int(args[1])
        if deg not in VALID_ROT:
            sys.exit("rotate must be one of %s" % (VALID_ROT,))
        cfg = load(path)
        set_rotation(cfg, deg)
        save(path, cfg)

    elif cmd == "show":
        print(json.dumps(load(path), indent=2))

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
