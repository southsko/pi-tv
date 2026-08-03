"""Phone-friendly web remote + file manager (Flask, served by the main service).

Endpoints:
  GET  /                  remote control page
  GET  /api/status        now playing, channel list, power, volume
  POST /api/pause         toggle play/pause
  POST /api/next          skip to next episode
  POST /api/power         toggle power (screen + amp)
  POST /api/channel       {"name": "..."} or {"step": 1}
  POST /api/volume        {"volume": 0-130}
  POST /api/upload        multipart: file + channel
  POST /api/rescan        rescan the videos directory
  GET  /api/files         all channels + files + sizes + disk free
  POST /api/delete        {"channel": "...", "name": "..."}
  POST /api/rename        {"channel", "name", "new_name"}
  POST /api/mkchannel     {"name": "..."}
  GET  /api/samba         share running state + mode (open/locked) + user
  POST /api/samba         {"enabled": true/false} start/stop the share
  POST /api/samba/auth    {"mode":"open"} or {"mode":"locked","user","password"}
"""
import os
import re
import shutil
import subprocess

from flask import Flask, jsonify, render_template_string, request


def _samba_state():
    """'on', 'off', or 'absent' (not installed / not set up)."""
    try:
        r = subprocess.run(["systemctl", "is-active", "smbd"],
                           capture_output=True, text=True, timeout=5)
        if r.stdout.strip() == "active":
            return "on"
        chk = subprocess.run(["systemctl", "list-unit-files", "smbd.service"],
                             capture_output=True, text=True, timeout=5)
        return "off" if "smbd.service" in chk.stdout else "absent"
    except (OSError, subprocess.TimeoutExpired):
        return "absent"


def _samba_set(on):
    verbs = ("start", "enable") if on else ("stop", "disable")
    for verb in verbs:
        subprocess.run(["sudo", "-n", "systemctl", verb, "smbd"],
                       capture_output=True, timeout=15)
    return _samba_state()


SHARE_AUTH_HELPER = "/usr/local/sbin/pitv-share-auth"


def _samba_auth():
    """Inspect the [videos] block of smb.conf.

    Returns (mode, user): mode is 'open' (guest access), 'locked' (login
    required), or None if the share/block isn't present. smb.conf is
    world-readable, so this needs no privileges.
    """
    try:
        with open("/etc/samba/smb.conf", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return (None, "")
    in_block = False
    guest = None
    user = ""
    for raw in lines:
        s = raw.strip()
        if s.startswith("["):
            in_block = (s.lower() == "[videos]")
            continue
        if not in_block or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key, val = key.strip().lower(), val.strip()
        if key == "guest ok":
            guest = val.lower() == "yes"
        elif key == "valid users":
            user = val
        elif key == "force user" and not user:
            user = val
    if guest is None:
        return (None, user)
    return (("open" if guest else "locked"), user)

PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simpsons TV Remote</title>
<style>
  :root { --bg:#1a1035; --panel:#2b1d55; --accent:#fbd000; --accent2:#e0453a; }
  * { box-sizing:border-box; font-family:Verdana,system-ui,sans-serif; }
  body { margin:0; background:var(--bg); color:#fff; padding:16px; max-width:480px;
         margin-inline:auto; }
  h1 { color:var(--accent); font-size:1.3em; text-align:center; margin:8px 0 2px; }
  #now { text-align:center; color:#cfc3f5; font-size:.85em; min-height:2.4em;
         margin-bottom:10px; word-break:break-word; }
  .panel { background:var(--panel); border-radius:14px; padding:14px; margin-bottom:12px; }
  .row { display:flex; gap:10px; }
  button { flex:1; padding:14px 6px; font-size:1em; border:0; border-radius:10px;
           background:var(--accent); color:#222; font-weight:bold; cursor:pointer; }
  button.alt { background:var(--accent2); color:#fff; }
  button.ghost { background:#453370; color:#fff; }
  button.mini { flex:0 0 auto; padding:6px 10px; font-size:.8em; }
  select,input[type=range],input[type=file],input[type=text],input[type=password] { width:100%; }
  select,input[type=text],input[type=password] { padding:10px; border-radius:8px; border:0;
           margin-top:6px; background:#453370; color:#fff; font-size:1em; }
  label { font-size:.8em; color:#cfc3f5; }
  #power.off { background:#555; color:#ccc; }
  progress { width:100%; height:6px; }
  .small { font-size:.75em; color:#9d8fd0; text-align:center; margin-top:4px; }
  .file { display:flex; align-items:center; gap:8px; padding:7px 4px;
          border-bottom:1px solid #3b2b6b; font-size:.85em; }
  .file span.name { flex:1; word-break:break-word; }
  .file span.size { color:#9d8fd0; font-size:.85em; white-space:nowrap; }
</style></head>
<body>
<h1>&#128250; Simpsons TV</h1>
<div id="now">&hellip;</div>
<div class="panel">
  <div class="row">
    <button id="power" class="alt" onclick="post('/api/power')">Power</button>
    <button onclick="post('/api/pause')" id="pause">Pause</button>
    <button onclick="post('/api/next')">Next &#9197;</button>
  </div>
</div>
<div class="panel">
  <label>Channel</label>
  <select id="channel" onchange="post('/api/channel',{name:this.value})"></select>
  <div class="row" style="margin-top:10px">
    <button class="ghost" onclick="post('/api/channel',{step:-1})">&#9664; Ch</button>
    <button class="ghost" onclick="post('/api/channel',{step:1})">Ch &#9654;</button>
  </div>
</div>
<div class="panel">
  <label>Volume <span id="volval"></span></label>
  <input type="range" id="vol" min="0" max="130" step="5"
         onchange="post('/api/volume',{volume:+this.value})">
</div>
<div class="panel">
  <label>Upload episode</label>
  <input type="file" id="file" accept="video/*" multiple>
  <select id="upch"></select>
  <input type="text" id="newch" placeholder="...or new channel name">
  <div class="row" style="margin-top:10px">
    <button onclick="upload()">Upload</button>
    <button class="ghost" onclick="post('/api/rescan')">Rescan</button>
  </div>
  <progress id="prog" value="0" max="100" style="display:none"></progress>
  <div class="small" id="upmsg"></div>
</div>
<div class="panel">
  <div class="row" style="align-items:center">
    <label style="flex:1">Network share (Samba)</label>
    <button id="samba" class="mini ghost" onclick="toggleSamba()">&hellip;</button>
  </div>
  <div class="small" id="sambamsg"></div>
  <div id="sambaauth" style="display:none;margin-top:10px">
    <div class="small" id="sambamode"></div>
    <input type="text" id="smbuser" placeholder="username" autocomplete="off"
           autocapitalize="off" spellcheck="false">
    <input type="password" id="smbpass" placeholder="password" autocomplete="new-password">
    <div class="row" style="margin-top:8px">
      <button class="mini" onclick="lockShare()">Require login</button>
      <button class="mini alt" onclick="openShare()">Make open</button>
    </div>
    <div class="small" id="sambaauthmsg"></div>
  </div>
</div>
<div class="panel">
  <label>Files</label>
  <select id="fmch" onchange="renderFiles()"></select>
  <div id="filelist"></div>
  <div class="row" style="margin-top:10px">
    <input type="text" id="mkch" placeholder="new channel folder">
    <button class="mini ghost" onclick="mkChannel()">Create</button>
  </div>
  <div class="small" id="disk"></div>
</div>
<script>
let filesData = {};
async function post(url, body) {
  const r = await fetch(url, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{})});
  refresh(); loadFiles();
  return r;
}
async function refresh() {
  try {
    const s = await (await fetch('/api/status')).json();
    document.getElementById('now').textContent =
      (s.power ? '' : '(off) ') + (s.now_playing || 'nothing playing') +
      ' — ch: ' + (s.channel || '?');
    document.getElementById('pause').textContent = s.paused ? 'Play' : 'Pause';
    document.getElementById('power').classList.toggle('off', !s.power);
    document.getElementById('vol').value = s.volume;
    document.getElementById('volval').textContent = s.volume;
    const sel = document.getElementById('channel');
    if ([...sel.options].map(o=>o.value).join()!==s.channels.join())
      sel.innerHTML = s.channels.map(c=>`<option>${c}</option>`).join('');
    sel.value = s.channel;
    const up = document.getElementById('upch');
    if ([...up.options].map(o=>o.value).join()!==s.channels.join())
      up.innerHTML = s.channels.map(c=>`<option>${c}</option>`).join('');
  } catch(e) {}
}
function fmtSize(b) {
  if (b > 1e9) return (b/1e9).toFixed(2)+' GB';
  if (b > 1e6) return (b/1e6).toFixed(1)+' MB';
  return Math.round(b/1e3)+' KB';
}
async function loadFiles() {
  try {
    const d = await (await fetch('/api/files')).json();
    filesData = d.channels;
    document.getElementById('disk').textContent =
      'free space: ' + fmtSize(d.free) + ' of ' + fmtSize(d.total);
    const sel = document.getElementById('fmch');
    const names = Object.keys(filesData);
    if ([...sel.options].map(o=>o.value).join()!==names.join()) {
      const cur = sel.value;
      sel.innerHTML = names.map(c=>`<option>${c}</option>`).join('');
      if (names.includes(cur)) sel.value = cur;
    }
    renderFiles();
  } catch(e) {}
}
function renderFiles() {
  const ch = document.getElementById('fmch').value;
  const list = filesData[ch] || [];
  document.getElementById('filelist').innerHTML = list.map(f => `
    <div class="file">
      <span class="name">${f.name}</span>
      <span class="size">${fmtSize(f.size)}</span>
      <button class="mini ghost" onclick="renameFile('${ch}','${f.name.replace(/'/g,"\\\\'")}')">&#9998;</button>
      <button class="mini alt" onclick="delFile('${ch}','${f.name.replace(/'/g,"\\\\'")}')">&#10005;</button>
    </div>`).join('') || '<div class="small">empty channel</div>';
}
async function delFile(ch, name) {
  if (!confirm('Delete "'+name+'" from '+ch+'?')) return;
  await post('/api/delete', {channel:ch, name:name});
}
async function renameFile(ch, name) {
  const n = prompt('Rename to:', name);
  if (n && n !== name) await post('/api/rename', {channel:ch, name:name, new_name:n});
}
let sambaState = 'absent';
async function loadSamba() {
  try {
    const d = await (await fetch('/api/samba')).json();
    sambaState = d.state;
    const btn = document.getElementById('samba');
    const msg = document.getElementById('sambamsg');
    const auth = document.getElementById('sambaauth');
    if (d.state === 'absent') {
      btn.textContent = 'n/a';
      msg.textContent = 'not set up — run setup_share.sh on the TV once';
      auth.style.display = 'none';
      return;
    }
    btn.textContent = d.state === 'on' ? 'ON' : 'OFF';
    btn.className = 'mini ' + (d.state === 'on' ? '' : 'alt');
    msg.textContent = d.state === 'on'
      ? 'visible as \\\\\\\\' + (d.host||'simpsonstv') + '\\\\videos' : 'share stopped';
    auth.style.display = 'block';
    const mode = document.getElementById('sambamode');
    if (d.mode === 'locked') {
      mode.textContent = 'Login required — user: ' + (d.user || '?');
      const u = document.getElementById('smbuser');
      if (!u.value) u.value = d.user || '';
    } else if (d.mode === 'open') {
      mode.textContent = 'Open — anyone on the network can read/write (no login)';
    } else {
      mode.textContent = '';
    }
  } catch(e) {}
}
async function toggleSamba() {
  if (sambaState === 'absent') return;
  await fetch('/api/samba', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({enabled: sambaState !== 'on'})});
  loadSamba();
}
async function lockShare() {
  const user = document.getElementById('smbuser').value.trim();
  const password = document.getElementById('smbpass').value;
  const m = document.getElementById('sambaauthmsg');
  if (!user || !password) { m.textContent = 'enter a username and password'; return; }
  m.textContent = 'saving…';
  const r = await fetch('/api/samba/auth', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({mode:'locked', user, password})});
  document.getElementById('smbpass').value = '';
  m.textContent = r.ok ? 'login set — reconnect with the new credentials'
                       : ('error: ' + (await r.text()));
  loadSamba();
}
async function openShare() {
  const m = document.getElementById('sambaauthmsg');
  if (!confirm('Make the share open to anyone on the network (no login)?')) return;
  m.textContent = 'saving…';
  const r = await fetch('/api/samba/auth', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({mode:'open'})});
  m.textContent = r.ok ? 'share is now open' : ('error: ' + (await r.text()));
  loadSamba();
}
async function mkChannel() {
  const n = document.getElementById('mkch').value.trim();
  if (n) { await post('/api/mkchannel', {name:n});
           document.getElementById('mkch').value=''; }
}
function upload() {
  const files = [...document.getElementById('file').files];
  if (!files.length) { document.getElementById('upmsg').textContent='Pick a file first'; return; }
  const ch = document.getElementById('newch').value.trim() ||
             document.getElementById('upch').value;
  const prog = document.getElementById('prog');
  prog.style.display = 'block';
  let done = 0;
  const sendNext = () => {
    if (!files.length) {
      prog.style.display='none';
      document.getElementById('upmsg').textContent = done+' file(s) uploaded';
      refresh(); loadFiles(); return;
    }
    const f = files.shift();
    const fd = new FormData();
    fd.append('file', f); fd.append('channel', ch);
    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = e => { if (e.lengthComputable) prog.value=100*e.loaded/e.total; };
    xhr.onload = () => {
      if (xhr.status===200) done++;
      else document.getElementById('upmsg').textContent='Failed: '+f.name;
      sendNext();
    };
    xhr.open('POST','/api/upload'); xhr.send(fd);
  };
  sendNext();
}
refresh(); loadFiles(); loadSamba();
setInterval(refresh, 3000);
</script>
</body></html>"""

VIDEO_EXTS = (".mp4", ".mkv", ".m4v", ".mov", ".avi", ".webm")


def safe_name(name):
    name = os.path.basename(name.replace("\\", "/"))
    return re.sub(r"[^A-Za-z0-9 ._-]", "_", name).strip() or "unnamed"


def create_app(tv):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB

    def channel_dir(channel, create=False):
        channel = safe_name(channel)
        base = tv.channels.videos_dir
        d = base if channel == "main" else os.path.join(base, channel)
        if create:
            os.makedirs(d, exist_ok=True)
        return d if os.path.isdir(d) else None

    @app.get("/")
    def index():
        return render_template_string(PAGE)

    @app.get("/api/status")
    def status():
        return jsonify(tv.status())

    @app.post("/api/pause")
    def pause():
        tv.toggle_pause()
        return jsonify(ok=True)

    @app.post("/api/next")
    def next_ep():
        tv.next_episode()
        return jsonify(ok=True)

    @app.post("/api/power")
    def power():
        tv.toggle_power()
        return jsonify(ok=True)

    @app.post("/api/channel")
    def channel():
        data = request.get_json(silent=True) or {}
        if "name" in data:
            tv.set_channel(data["name"])
        else:
            tv.change_channel(int(data.get("step", 1)))
        return jsonify(ok=True)

    @app.post("/api/volume")
    def volume():
        data = request.get_json(silent=True) or {}
        tv.set_volume(data.get("volume", 100))
        return jsonify(ok=True)

    @app.post("/api/rescan")
    def rescan():
        tv.channels.rescan()
        return jsonify(ok=True)

    @app.get("/api/samba")
    def samba_status():
        import socket
        mode, user = _samba_auth()
        return jsonify(state=_samba_state(), host=socket.gethostname(),
                       mode=mode, user=user)

    @app.post("/api/samba")
    def samba_toggle():
        data = request.get_json(silent=True) or {}
        state = _samba_set(bool(data.get("enabled")))
        return jsonify(state=state)

    @app.post("/api/samba/auth")
    def samba_auth():
        """Switch the share to open (guest) or locked (username + password).

        The privileged work (creating the user, setting the Samba password,
        rewriting smb.conf) is done by the root-owned helper, which the web UI
        is allowed to run via a scoped NOPASSWD sudoers rule. The username is
        validated again inside the helper; the password is passed on stdin so
        it never shows up in the process list.
        """
        if not os.path.exists(SHARE_AUTH_HELPER):
            return "share auth not set up — run setup_share.sh on the TV", 501
        data = request.get_json(silent=True) or {}
        mode = data.get("mode")
        try:
            if mode == "open":
                r = subprocess.run(["sudo", "-n", SHARE_AUTH_HELPER, "open"],
                                   capture_output=True, text=True, timeout=30)
            elif mode == "locked":
                user = (data.get("user") or "").strip()
                password = data.get("password") or ""
                if not user or not password:
                    return "username and password required", 400
                r = subprocess.run(["sudo", "-n", SHARE_AUTH_HELPER, "lock", user],
                                   input=password, capture_output=True,
                                   text=True, timeout=30)
            else:
                return "bad mode", 400
        except subprocess.TimeoutExpired:
            return "timed out", 504
        if r.returncode != 0:
            return (r.stderr.strip() or "failed"), 500
        new_mode, new_user = _samba_auth()
        return jsonify(ok=True, mode=new_mode, user=new_user)

    # -- file manager ------------------------------------------------------

    @app.get("/api/files")
    def files():
        base = tv.channels.videos_dir
        out = {}

        def scan(name, path):
            entries = []
            try:
                for f in sorted(os.listdir(path)):
                    full = os.path.join(path, f)
                    if os.path.isfile(full) and f.lower().endswith(VIDEO_EXTS):
                        entries.append({"name": f, "size": os.path.getsize(full)})
            except OSError:
                pass
            out[name] = entries

        if os.path.isdir(base):
            loose = [f for f in os.listdir(base)
                     if f.lower().endswith(VIDEO_EXTS)
                     and os.path.isfile(os.path.join(base, f))]
            if loose:
                scan("main", base)
            for entry in sorted(os.listdir(base)):
                p = os.path.join(base, entry)
                if os.path.isdir(p):
                    scan(entry, p)
        usage = shutil.disk_usage(base if os.path.isdir(base) else "/")
        return jsonify(channels=out, free=usage.free, total=usage.total)

    @app.post("/api/delete")
    def delete():
        data = request.get_json(silent=True) or {}
        d = channel_dir(data.get("channel", ""))
        if not d:
            return "no such channel", 404
        target = os.path.join(d, safe_name(data.get("name", "")))
        if not os.path.isfile(target):
            return "no such file", 404
        os.remove(target)
        tv.channels.rescan()
        return jsonify(ok=True)

    @app.post("/api/rename")
    def rename():
        data = request.get_json(silent=True) or {}
        d = channel_dir(data.get("channel", ""))
        if not d:
            return "no such channel", 404
        src = os.path.join(d, safe_name(data.get("name", "")))
        dst = os.path.join(d, safe_name(data.get("new_name", "")))
        if not os.path.isfile(src):
            return "no such file", 404
        if os.path.exists(dst):
            return "target exists", 409
        os.rename(src, dst)
        tv.channels.rescan()
        return jsonify(ok=True)

    @app.post("/api/mkchannel")
    def mkchannel():
        data = request.get_json(silent=True) or {}
        name = safe_name(data.get("name", ""))
        if name in ("", "unnamed", "main"):
            return "bad name", 400
        os.makedirs(os.path.join(tv.channels.videos_dir, name), exist_ok=True)
        return jsonify(ok=True)

    @app.post("/api/upload")
    def upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return "no file", 400
        channel = safe_name(request.form.get("channel") or "main")
        fname = safe_name(f.filename)
        dest_dir = channel_dir(channel, create=True)
        f.save(os.path.join(dest_dir, fname))
        tv.channels.rescan()
        return jsonify(ok=True, saved=fname, channel=channel)

    return app
