"""Channel + playlist management.

Every subfolder of the videos directory that contains at least one video
file is a "channel". Episodes within a channel play in shuffled order
without repeats until the whole channel has been seen, then reshuffle.
Last-used channel and volume persist across reboots in state.json.
"""
import json
import os
import random
import threading

VIDEO_EXTS = (".mp4", ".mkv", ".m4v", ".mov", ".avi", ".webm")


class Channel:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self._queue = []

    def episodes(self):
        try:
            return sorted(
                os.path.join(self.path, f)
                for f in os.listdir(self.path)
                if f.lower().endswith(VIDEO_EXTS) and not f.startswith(".")
            )
        except OSError:
            return []

    def next_episode(self):
        if not self._queue:
            eps = self.episodes()
            random.shuffle(eps)
            self._queue = eps
        if not self._queue:
            return None
        return self._queue.pop(0)


class ChannelManager:
    def __init__(self, videos_dir, state_path):
        self.videos_dir = videos_dir
        self.state_path = state_path
        self._lock = threading.Lock()
        self.channels = []
        self.index = 0
        self.volume = 100
        self.rescan()
        self._load_state()

    def rescan(self):
        with self._lock:
            current = self.current_channel_name()
            found = []
            if os.path.isdir(self.videos_dir):
                for entry in sorted(os.listdir(self.videos_dir)):
                    path = os.path.join(self.videos_dir, entry)
                    if os.path.isdir(path):
                        ch = Channel(entry, path)
                        if ch.episodes():
                            found.append(ch)
                # Loose files directly in videos/ become an implicit channel,
                # for compatibility with the original layout.
                loose = Channel("main", self.videos_dir)
                if loose.episodes():
                    found.insert(0, loose)
            self.channels = found
            self.index = 0
            for i, ch in enumerate(self.channels):
                if ch.name == current:
                    self.index = i
                    break

    # -- state -----------------------------------------------------------

    def _load_state(self):
        try:
            with open(self.state_path) as f:
                state = json.load(f)
        except (OSError, ValueError):
            return
        self.volume = int(state.get("volume", 100))
        wanted = state.get("channel")
        for i, ch in enumerate(self.channels):
            if ch.name == wanted:
                self.index = i
                break

    def save_state(self):
        state = {"channel": self.current_channel_name(), "volume": self.volume}
        tmp = self.state_path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # -- queries / actions -------------------------------------------------

    def current_channel(self):
        if not self.channels:
            return None
        return self.channels[self.index % len(self.channels)]

    def current_channel_name(self):
        ch = self.current_channel()
        return ch.name if ch else None

    def channel_names(self):
        return [ch.name for ch in self.channels]

    def next_episode(self):
        with self._lock:
            ch = self.current_channel()
            return ch.next_episode() if ch else None

    def change_channel(self, step=1):
        with self._lock:
            if not self.channels:
                return None
            self.index = (self.index + step) % len(self.channels)
        self.save_state()
        return self.current_channel_name()

    def set_channel(self, name):
        with self._lock:
            for i, ch in enumerate(self.channels):
                if ch.name == name:
                    self.index = i
                    break
            else:
                return None
        self.save_state()
        return name

    def set_volume(self, volume):
        self.volume = max(0, min(130, int(volume)))
        self.save_state()
        return self.volume
