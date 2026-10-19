"""Keep one display frame and at most one queued GUI notification."""
from threading import Lock


class DisplayMailbox:
    def __init__(self):
        self._lock = Lock()
        self._jpeg = None
        self._notified = False

    def offer(self, jpeg):
        with self._lock:
            self._jpeg = jpeg
            if self._notified:
                return False
            self._notified = True
            return True

    def take(self):
        with self._lock:
            jpeg, self._jpeg = self._jpeg, None
            self._notified = False
            return jpeg


class ImageRequestState:
    """One evidence fetch at a time; reject replies for a replaced camera/capture."""

    def __init__(self):
        self.wanted = None
        self.inflight = None
        self.shown = None

    def request(self, key):
        self.wanted = key
        if key is None:
            self.shown = None
        if key is None or self.inflight is not None or key == self.shown:
            return False
        self.inflight = key
        return True

    def complete(self, key, success):
        if self.inflight != key:
            return False
        self.inflight = None
        current = self.wanted == key
        if current and success:
            self.shown = key
        return current and success
