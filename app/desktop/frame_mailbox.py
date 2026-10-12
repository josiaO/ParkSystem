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
