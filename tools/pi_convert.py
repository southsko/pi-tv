#!/usr/bin/env python3
"""Pi TV Converter — interactive ffmpeg batch converter.

A DOS-style file browser (tag clips with Space, F2 to convert) that re-encodes
the selected videos into the format the Pi TV player's hardware decoder plays
smoothly: H.264 baseline 480p + stereo AAC. Output lands in an ./encoded/
folder next to the sources.

Run on your PC (never the Pi — encoding is far too slow there):
    pip install colorama            # optional, nicer colours
    pip install windows-curses      # Windows only, for the browser
    python3 pi_convert.py

Adapted from southsko/drone-footage-merger.
"""
import glob
import os
import subprocess
import sys
import tempfile
import time

# ── quality knobs (env-overridable) ───────────────────────────────────────────
HEIGHT = os.environ.get("HEIGHT", "480")
CRF = os.environ.get("CRF", "23")
PRESET = os.environ.get("PRESET", "fast")
OUTPUT_SUBDIR = "encoded"

_CPU_VARGS = ['-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0',
              '-preset', PRESET, '-crf', CRF, '-pix_fmt', 'yuv420p']


def _encoder_listed(codec):
    """Is this encoder compiled into the ffmpeg on PATH at all?"""
    try:
        r = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'],
                           capture_output=True, text=True, timeout=15)
        return codec in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def _encoder_works(vargs):
    """Return (ok, last_error_line) from a tiny real test encode."""
    try:
        # 320x240 (not 64x64 — NVENC has a minimum frame size and rejects tiny)
        r = subprocess.run(
            ['ffmpeg', '-hide_banner', '-f', 'lavfi', '-i',
             'color=c=black:s=320x240:d=0.3'] + vargs
            + ['-f', 'null', '-'],
            capture_output=True, text=True, timeout=25)
        if r.returncode == 0:
            return True, ""
        lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
        return False, (lines[-1] if lines else "unknown error")
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _pick_vcodec():
    """Auto-detect a working GPU encoder; fall back to CPU only if none.

    Each present GPU encoder is test-run; if it's in the ffmpeg build but the
    test fails, the reason is printed so the CPU fallback isn't a mystery.
    Modern GPUs (Ampere+) dropped H.264 baseline, so GPU paths use High
    profile — the Pi's VideoCore decoder handles it fine.
    """
    candidates = [
        ('h264_nvenc',
         ['-c:v', 'h264_nvenc', '-profile:v', 'high', '-level', '4.0',
          '-preset', 'p4', '-cq', CRF, '-pix_fmt', 'yuv420p'], 'GPU (NVENC)'),
        ('h264_qsv',
         ['-c:v', 'h264_qsv', '-profile:v', 'high',
          '-global_quality', CRF, '-pix_fmt', 'nv12'], 'GPU (QSV)'),
        ('h264_amf',
         ['-c:v', 'h264_amf', '-profile:v', 'high', '-rc', 'cqp',
          '-qp_i', CRF, '-qp_p', CRF, '-pix_fmt', 'yuv420p'], 'GPU (AMF)'),
    ]
    any_listed = False
    for codec, vargs, label in candidates:
        if not _encoder_listed(codec):
            continue
        any_listed = True
        ok, why = _encoder_works(vargs)
        if ok:
            return vargs, label
        warn(f"{label} present but test failed → {why}")
    if not any_listed:
        warn("This ffmpeg build has no GPU encoders — get a full build "
             "(gyan.dev 'full' or BtbN) to use your GPU.")
    return _CPU_VARGS, 'CPU'

# ── colorama ──────────────────────────────────────────────────────────────────
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False
    class _D:
        def __getattr__(self, _): return ''
    Fore = Back = Style = _D()

# ── curses (needs 'windows-curses' on Windows) ────────────────────────────────
try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

VIDEO_EXTENSIONS = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.m4v', '*.webm',
                    '*.flv', '*.wmv', '*.MP4', '*.MOV', '*.AVI', '*.MKV']
_VIDEO_EXTS = {os.path.splitext(p)[1].lower() for p in VIDEO_EXTENSIONS}

BANNER = f"""
{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}
  ╔══════════════════════════════════════════════════════════╗
  ║          📺  PI TV CONVERTER  v1.0                       ║
  ║        480p H.264 baseline + AAC · Powered by FFmpeg     ║
  ╚══════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""


def info(m):  print(f"{Fore.CYAN}{Style.BRIGHT}[INFO]{Style.RESET_ALL}  {m}")
def warn(m):  print(f"{Fore.YELLOW}{Style.BRIGHT}[WARN]{Style.RESET_ALL}  {m}")
def err(m):   print(f"{Fore.RED}{Style.BRIGHT}[ERR] {Style.RESET_ALL}  {m}")
def ok(m):    print(f"{Fore.GREEN}{Style.BRIGHT}[OK]  {Style.RESET_ALL}  {m}")
def div():    print(f"{Fore.BLUE}{Style.BRIGHT}{'─'*62}{Style.RESET_ALL}")


# ── file discovery (text fallback only) ───────────────────────────────────────
def find_video_files():
    files, seen, unique = [], set(), []
    for pat in VIDEO_EXTENSIONS:
        files.extend(glob.glob(pat))
    for f in sorted(files):
        k = f.lower()
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique


def _get_dir_entries(directory):
    """(kind, name, full_path) tuples; dirs before video files."""
    entries = []
    parent = os.path.dirname(directory)
    if os.path.normcase(parent) != os.path.normcase(directory):
        entries.append(('up', '..', parent))
    try:
        items = sorted(os.listdir(directory), key=str.lower)
    except (PermissionError, OSError):
        return entries
    dirs, vids = [], []
    for item in items:
        full = os.path.join(directory, item)
        if os.path.isdir(full):
            dirs.append(('dir', item, full))
        elif os.path.splitext(item)[1].lower() in _VIDEO_EXTS:
            vids.append(('file', item, full))
    entries.extend(dirs)
    entries.extend(vids)
    return entries


# ── DOS-style navigable file browser ──────────────────────────────────────────
def _curses_selector(stdscr, start_dir, pick_dir=False):
    curses.curs_set(0)
    curses.start_color()
    HAS_CLR = curses.has_colors()
    if HAS_CLR:
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE,  curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_CYAN,   curses.COLOR_BLUE)
        curses.init_pair(4, curses.COLOR_BLACK,  curses.COLOR_WHITE)
        curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        C_BLUE = curses.color_pair(1)
        C_TAG  = curses.color_pair(2) | curses.A_BOLD
        C_DIR  = curses.color_pair(3) | curses.A_BOLD
        C_BAR  = curses.color_pair(4) | curses.A_BOLD
        C_FNUM = curses.color_pair(5) | curses.A_BOLD
        C_FLAB = curses.color_pair(4)
    else:
        C_BLUE = curses.A_NORMAL
        C_TAG = C_DIR = C_FNUM = curses.A_BOLD
        C_BAR = curses.A_REVERSE
        C_FLAB = curses.A_NORMAL

    def load(d):
        e = _get_dir_entries(d)
        return [x for x in e if x[0] in ('up', 'dir')] if pick_dir else e

    current_dir = start_dir
    tagged, cursor, scroll = {}, 0, 0
    entries = load(current_dir)

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()
        W = w - 1
        ENTRY_TOP, ENTRY_BOT = 2, h - 3
        list_h = max(0, ENTRY_BOT - ENTRY_TOP + 1)

        if HAS_CLR:
            for r in range(h - 2):
                try: stdscr.addstr(r, 0, ' ' * W, C_BLUE)
                except Exception: pass
        try: stdscr.addstr(0, 0, (' ' + current_dir)[:W].ljust(W), C_BAR)
        except Exception: pass
        try: stdscr.addstr(1, 0, ('=' * W)[:W], curses.A_BOLD)
        except Exception: pass

        for idx, (kind, name, full_path) in enumerate(entries[scroll:scroll + list_h]):
            abs_i = scroll + idx
            is_cur = abs_i == cursor
            row = ENTRY_TOP + idx
            if kind in ('up', 'dir'):
                body = '<DIR>  ' + name
                attr = curses.A_REVERSE if is_cur else C_DIR
            else:
                mark = '[*]' if full_path in tagged else '[ ]'
                body = mark + '  ' + name
                attr = (curses.A_REVERSE if is_cur
                        else C_TAG if full_path in tagged else curses.A_BOLD)
            line = (('> ' if is_cur else '  ') + body)[:W].ljust(W)
            try: stdscr.addstr(row, 0, line, attr)
            except Exception: pass

        if pick_dir:
            hint = '  Enter=open folder  Bksp=up  F2=CHOOSE THIS FOLDER  Q=cancel'
        else:
            hint = ('  ' + str(len(tagged)) + ' tagged  |  Sp=tag  Enter=open  '
                    'Bksp=up  A=all  F2=convert  Q=quit')
        try: stdscr.addstr(h - 2, 0, hint[:W].ljust(W), C_BAR)
        except Exception: pass

        try: stdscr.addstr(h - 1, 0, ' ' * W, C_FLAB)
        except Exception: pass
        x = 0
        fkeys = ([('2','Choose'),('10','Cancel')] if pick_dir
                 else [('2','Convert'),('5','TagAll'),('8','Clear'),('10','Quit')])
        for num, lbl in fkeys:
            seg = num + lbl + '  '
            if x + len(seg) > W: break
            try:
                stdscr.addstr(h - 1, x, num, C_FNUM)
                stdscr.addstr(h - 1, x + len(num), lbl + '  ', C_FLAB)
            except Exception: pass
            x += len(seg)

        stdscr.refresh()
        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
            if cursor > 0:
                cursor -= 1
                if cursor < scroll: scroll = cursor
        elif key in (curses.KEY_DOWN, ord('j')):
            if cursor < len(entries) - 1:
                cursor += 1
                if cursor >= scroll + list_h: scroll = cursor - list_h + 1
        elif key == curses.KEY_PPAGE:
            cursor = max(0, cursor - list_h); scroll = max(0, scroll - list_h)
        elif key == curses.KEY_NPAGE:
            cursor = min(len(entries) - 1, cursor + list_h)
            if cursor >= scroll + list_h: scroll = cursor - list_h + 1
        elif key == curses.KEY_HOME:
            cursor = scroll = 0
        elif key == curses.KEY_END:
            cursor = max(0, len(entries) - 1)
            scroll = max(0, cursor - list_h + 1)
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r'), curses.KEY_RIGHT):
            if entries:
                kind, name, full_path = entries[cursor]
                if kind in ('up', 'dir'):
                    current_dir = full_path
                    entries = load(current_dir)
                    cursor = scroll = 0
                elif not pick_dir:
                    tagged.pop(full_path, None) if full_path in tagged \
                        else tagged.__setitem__(full_path, True)
        elif key in (curses.KEY_BACKSPACE, curses.KEY_LEFT, 8, 127, 263):
            parent = os.path.dirname(current_dir)
            if os.path.normcase(parent) != os.path.normcase(current_dir):
                current_dir = parent
                entries = load(current_dir)
                cursor = scroll = 0
        elif key == ord(' '):
            if entries:
                kind, name, full_path = entries[cursor]
                if kind == 'file':
                    tagged.pop(full_path, None) if full_path in tagged \
                        else tagged.__setitem__(full_path, True)
        elif key in (curses.KEY_F5, ord('a'), ord('A')):
            fps = [fp for k, _, fp in entries if k == 'file']
            if fps and all(fp in tagged for fp in fps):
                for fp in fps: tagged.pop(fp, None)
            else:
                for fp in fps: tagged[fp] = True
        elif key == curses.KEY_F8:
            for k, _, fp in entries:
                if k == 'file': tagged.pop(fp, None)
        elif key in (curses.KEY_F2, ord('m'), ord('M'), ord('c'), ord('C')):
            return current_dir if pick_dir else list(tagged.keys())
        elif key in (curses.KEY_F10, ord('q'), ord('Q')):
            return None


def interactive_select(files):
    if not HAS_CURSES:
        warn("curses not available. On Windows:  pip install windows-curses")
        warn("Falling back to text input.\n")
        return fallback_select(files)
    result = curses.wrapper(_curses_selector, os.getcwd())
    return [] if result is None else result


def interactive_pick_dir(start):
    if not HAS_CURSES:
        return None
    return curses.wrapper(_curses_selector, start, True)


def _videos_under(folder):
    """All videos under folder, recursively; skips 'sample' files/folders."""
    found = []
    for dp, dn, files in os.walk(folder):
        dn[:] = [d for d in dn if "sample" not in d.lower()]
        for f in files:
            if (os.path.splitext(f)[1].lower() in _VIDEO_EXTS
                    and "sample" not in f.lower()
                    and not f.startswith(".")):
                found.append(os.path.join(dp, f))
    return sorted(found)


# ── native GUI picker (tkinter — bundled with Python, best on Windows) ────────
def gui_select():
    """Return (files, out_dir) via native dialogs, or (None, None) if cancelled
    or GUI unavailable."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception:
        return None, None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
    except Exception:
        return None, None

    # folder (whole season) or individual files?
    mode = messagebox.askyesnocancel(
        "Pi TV Converter",
        "Convert an entire folder?\n\n"
        "Yes  =  pick a FOLDER (all videos in it and subfolders)\n"
        "No   =  pick individual files\n"
        "Cancel  =  quit")
    if mode is None:
        root.destroy()
        return None, None

    if mode:  # folder
        src = filedialog.askdirectory(title="Select the folder of videos")
        if not src:
            root.destroy()
            return None, None
        files = _videos_under(src)
        if not files:
            messagebox.showwarning("Pi TV Converter",
                                   "No videos found in that folder.")
            root.destroy()
            return None, None
    else:     # individual files
        files = list(filedialog.askopenfilenames(
            title="Select videos (Ctrl/Shift-click for many)",
            filetypes=[("Video files",
                        "*.mp4 *.mkv *.mov *.avi *.m4v *.webm *.flv *.wmv"),
                       ("All files", "*.*")]))
        if not files:
            root.destroy()
            return None, None

    default_out = os.environ.get("PI_TV_OUT") or _output_dir(files)
    out = filedialog.askdirectory(
        title="Select OUTPUT folder (Cancel = default 'encoded')",
        initialdir=os.path.dirname(default_out) or os.getcwd())
    root.destroy()
    return files, (out or default_out)


def choose_output(default):
    """Let the user keep the default, paste a path, or browse to a folder."""
    print()
    info(f"Default output: {Fore.WHITE}{Style.BRIGHT}{default}{Style.RESET_ALL}")
    prompt = (f"{Fore.YELLOW}Output folder — ENTER=default"
              + (", B=browse" if HAS_CURSES else "")
              + f", or paste a path:{Style.RESET_ALL} ")
    resp = input(prompt).strip().strip('"').strip("'")
    if resp == "":
        return default
    if resp.lower() == "b" and HAS_CURSES:
        picked = interactive_pick_dir(os.path.dirname(default) or os.getcwd())
        return picked or default
    path = os.path.abspath(os.path.expanduser(resp))
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
            info(f"Created {path}")
        except OSError as e:
            warn(f"Can't use {path} ({e}); using default.")
            return default
    return path


def fallback_select(files):
    print("\n--- Videos in this folder ---")
    for i, f in enumerate(files):
        print(f"  [{i+1}] {os.path.basename(f)}")
    print("Enter numbers (e.g. 1,3,4) or ALL / DONE:\n")
    while True:
        s = input("> ").strip()
        if s.upper() == 'DONE': return []
        if s.upper() == 'ALL':  return files
        try:
            idxs = [int(x.strip())-1 for x in s.split(',') if x.strip()]
            if all(0 <= i < len(files) for i in idxs):
                return [files[i] for i in idxs]
            warn("Invalid index.")
        except ValueError:
            warn("Use comma-separated numbers.")


# ── convert ───────────────────────────────────────────────────────────────────
def _output_dir(selected):
    paths = [os.path.abspath(f) for f in selected]
    common = os.path.commonpath(paths)
    base = common if os.path.isdir(common) else os.path.dirname(common)
    return os.path.join(base, OUTPUT_SUBDIR)


def _probe_duration(path):
    """Length of a video in seconds (0 if unknown)."""
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', path], capture_output=True, text=True)
        return float(r.stdout.strip())
    except (ValueError, OSError):
        return 0.0


def _bar(frac, width=22):
    frac = max(0.0, min(1.0, frac))
    fill = int(frac * width)
    return '[' + '#' * fill + '-' * (width - fill) + ']'


def _fmt(secs):
    secs = int(max(0, secs))
    if secs >= 3600:
        return "%d:%02d:%02d" % (secs // 3600, (secs % 3600) // 60, secs % 60)
    return "%d:%02d" % (secs // 60, secs % 60)


def _convert_one(src, out, label, vargs, files_left=0, avg_wall=None):
    """Run ffmpeg with a live progress bar. Returns True on success.

    files_left = whole files still queued after this one.
    avg_wall   = mean wall-seconds per finished file so far (None until known).
    """
    dur = _probe_duration(src)
    cmd = ['ffmpeg', '-y', '-i', src, '-vf', 'scale=-2:%s' % HEIGHT] \
        + vargs \
        + ['-c:a', 'aac', '-ac', '2', '-b:a', '128k',
           '-movflags', '+faststart',
           '-progress', 'pipe:1', '-nostats', out]
    errf = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                text=True, bufsize=1)
    except FileNotFoundError:
        errf.close()
        raise

    cur, fps, speed = 0.0, 0.0, 0.0
    for line in proc.stdout:
        line = line.strip()
        if line.startswith('out_time='):
            ts = line.split('=', 1)[1]
            try:
                hh, mm, ss = ts.split(':')
                cur = int(hh) * 3600 + int(mm) * 60 + float(ss)
            except ValueError:
                pass
        elif line.startswith('fps='):
            try:
                fps = float(line.split('=', 1)[1])
            except ValueError:
                pass
        elif line.startswith('speed='):
            try:
                speed = float(line.split('=', 1)[1].rstrip('x'))
            except ValueError:
                pass
        elif not line.startswith('progress='):
            continue  # only redraw on the last key of each progress block

        rate = "%4.0ffps" % fps if fps else "  --fps"
        # ETA for this file, from ffmpeg's own speed multiplier
        file_eta = (dur - cur) / speed if (dur > 0 and speed > 0) else None
        # ETA for the whole queue: this file's remaining + avg per remaining file
        q_eta = None
        if avg_wall:
            q_eta = avg_wall * files_left + (file_eta if file_eta is not None
                                            else avg_wall)
        f_txt = "ETA " + _fmt(file_eta) if file_eta is not None else "ETA --"
        q_txt = "Q " + _fmt(q_eta) if q_eta is not None else "Q --"
        if dur > 0:
            frac = cur / dur
            msg = "  %s  %s %3d%%  %.0ffps %.1fx  %s  %s" % (
                label, _bar(frac), int(frac * 100), fps, speed, f_txt, q_txt)
        else:
            msg = "  %s  %ds  %.0ffps %.1fx  %s" % (
                label, int(cur), fps, speed, q_txt)
        sys.stdout.write("\r" + msg[:110].ljust(110))
        sys.stdout.flush()
    proc.wait()
    sys.stdout.write("\r" + " " * 110 + "\r")   # wipe the progress line
    sys.stdout.flush()

    if proc.returncode != 0:
        errf.seek(0)
        tail = errf.read().decode('utf-8', 'replace').strip().splitlines()[-2:]
        errf.close()
        for ln in tail:
            print("      %s" % ln)
        return False
    errf.close()
    return True


def run_convert(selected, out_dir):
    if not selected:
        warn("No files selected.")
        return

    os.makedirs(out_dir, exist_ok=True)

    print(); info("Detecting GPU encoder...")
    vargs, enc = _pick_vcodec()
    is_gpu = enc.startswith("GPU")

    print(); div()
    print(f"{Fore.CYAN}{Style.BRIGHT}  📺  CONVERTING {len(selected)} CLIP(S) → {HEIGHT}p Pi TV{Style.RESET_ALL}")
    info(f"Output  →  {Fore.WHITE}{Style.BRIGHT}{out_dir}{Style.RESET_ALL}")
    info(f"Encoder →  {Fore.WHITE}{Style.BRIGHT}{enc}{Style.RESET_ALL}")
    div(); print()

    done_names, ok_n, fail_n, skip_n = set(), 0, 0, 0
    total = len(selected)
    wall_done, files_done = 0.0, 0     # for the queue ETA
    for i, src in enumerate(sorted(selected), 1):
        base = os.path.splitext(os.path.basename(src))[0]
        name = base + ".mp4"
        if name in done_names:
            n = 2
            while f"{base} ({n}).mp4" in done_names:
                n += 1
            name = f"{base} ({n}).mp4"
        done_names.add(name)
        out = os.path.join(out_dir, name)

        counter = f"[{i}/{total}]"
        if os.path.isfile(out):
            print(f"  {Fore.YELLOW}skip{Style.RESET_ALL} {counter} {name} (exists)")
            skip_n += 1
            continue

        # short label for the progress line (keep the episode-ish bit)
        short = base if len(base) <= 34 else base[:31] + "..."
        label = f"{counter} {short}"
        avg_wall = (wall_done / files_done) if files_done else None
        files_left = total - i          # whole files after this one
        t0 = time.time()
        try:
            success = _convert_one(src, out, label, vargs, files_left, avg_wall)
            if not success and is_gpu:
                warn("GPU failed on this file — retrying on CPU")
                if os.path.isfile(out):
                    os.remove(out)
                success = _convert_one(src, out, label, _CPU_VARGS,
                                       files_left, avg_wall)
        except FileNotFoundError:
            err("'ffmpeg'/'ffprobe' not found — install it / check PATH.")
            return
        wall_done += time.time() - t0
        files_done += 1
        if success:
            ok_n += 1
            print(f"  {Fore.GREEN}done{Style.RESET_ALL} {counter} {name}")
        else:
            fail_n += 1
            if os.path.isfile(out):
                os.remove(out)
            print(f"  {Fore.RED}FAIL{Style.RESET_ALL} {counter} {name}")

    print(); div()
    ok(f"{ok_n} converted, {skip_n} skipped, {fail_n} failed  →  {out_dir}")
    div()


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if not HAS_COLOR:
        print("[NOTE] pip install colorama  for coloured output")
    print(BANNER)

    use_tui = os.environ.get("PI_TV_TUI")   # set to force the text/curses browser
    selected, out_dir = (None, None)

    if not use_tui:
        selected, out_dir = gui_select()    # native dialogs (Windows-friendly)

    if selected is None:                    # GUI unavailable/cancelled → browser
        input(f"{Fore.YELLOW}  Press ENTER to open the file browser...{Style.RESET_ALL}  ")
        selected = interactive_select(find_video_files())
        if selected:
            default_out = os.environ.get("PI_TV_OUT") or _output_dir(selected)
            out_dir = choose_output(os.path.abspath(default_out))

    print(BANNER)
    if not selected:
        warn("Nothing selected — nothing to do.")
    else:
        info(f"{len(selected)} clip(s) selected:")
        for f in selected:
            print(f"  {Fore.WHITE}→  {os.path.basename(f)}{Style.RESET_ALL}")
        run_convert(selected, out_dir)

    print(); div()
    input(f"{Fore.GREEN}✅  Done. Press ENTER to exit...{Style.RESET_ALL}  ")


if __name__ == "__main__":
    main()
