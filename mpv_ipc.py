"""Minimal mpv JSON-IPC client (stdlib only).

Spawns mpv in idle mode and talks to it over a unix socket.
Replaces the deprecated omxplayer used by the original simpsonstv.
"""
import json
import os
import socket
import subprocess
import threading
import time


class MPVError(Exception):
    pass


class MPV:
    def __init__(self, socket_path="/tmp/simpsonstv-mpv.sock", extra_args=None,
                 event_handler=None):
        self.socket_path = socket_path
        self.event_handler = event_handler
        self._sock = None
        self._proc = None
        self._req_id = 0
        self._lock = threading.Lock()
        self._responses = {}
        self._resp_cond = threading.Condition()
        self._buffer = b""
        self._running = False
        self._extra_args = extra_args or []

    # -- lifecycle -----------------------------------------------------

    def start(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        args = [
            "mpv",
            "--idle=yes",
            "--force-window=no",
            "--fullscreen",
            "--no-osc",
            "--no-osd-bar",
            "--osd-level=0",
            "--no-input-default-bindings",
            "--no-input-cursor",
            "--cursor-autohide=always",
            "--keep-open=no",
            "--input-ipc-server=" + self.socket_path,
        ] + self._extra_args
        self._proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Wait for the IPC socket to appear
        deadline = time.time() + 15
        while not os.path.exists(self.socket_path):
            if time.time() > deadline:
                raise MPVError("mpv IPC socket never appeared")
            if self._proc.poll() is not None:
                raise MPVError("mpv exited on startup (code %s)"
                               % self._proc.returncode)
            time.sleep(0.1)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self.socket_path)
        self._running = True
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        try:
            self.command("quit")
        except Exception:
            pass
        if self._proc:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    # -- wire protocol -------------------------------------------------

    def _reader(self):
        while self._running:
            try:
                data = self._sock.recv(4096)
            except OSError:
                break
            if not data:
                break
            self._buffer += data
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "request_id" in msg:
                    with self._resp_cond:
                        self._responses[msg["request_id"]] = msg
                        self._resp_cond.notify_all()
                elif "event" in msg and self.event_handler:
                    try:
                        self.event_handler(msg)
                    except Exception:
                        pass

    def command(self, *cmd, timeout=5.0):
        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            payload = json.dumps(
                {"command": list(cmd), "request_id": req_id}) + "\n"
            self._sock.sendall(payload.encode("utf-8"))
        deadline = time.time() + timeout
        with self._resp_cond:
            while req_id not in self._responses:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise MPVError("timeout waiting for mpv reply to %r" % (cmd,))
                self._resp_cond.wait(remaining)
            resp = self._responses.pop(req_id)
        if resp.get("error") not in (None, "success"):
            raise MPVError("mpv error for %r: %s" % (cmd, resp.get("error")))
        return resp.get("data")

    # -- conveniences ----------------------------------------------------

    def loadfile(self, path):
        self.command("loadfile", path, "replace")

    def get(self, prop, default=None):
        try:
            return self.command("get_property", prop)
        except MPVError:
            return default

    def set(self, prop, value):
        self.command("set_property", prop, value)
