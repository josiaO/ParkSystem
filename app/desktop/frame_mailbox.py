"""Keep one display frame and at most one queued GUI notification."""
from threading import Lock


class DisplayMailbox:
    def __init__(self):
        self._lock = Lock()
        self._jpeg = None
        self._seq = None
        self._notified = False

    def offer(self, jpeg, seq=None):
        with self._lock:
            self._jpeg = jpeg
            self._seq = seq
            if self._notified:
                return False
            self._notified = True
            return True

    def take(self):
        return self.take_with_seq()[0]

    def take_with_seq(self):
        """(jpeg, camera frame number or None) of the newest offered frame."""
        with self._lock:
            jpeg, self._jpeg = self._jpeg, None
            seq, self._seq = self._seq, None
            self._notified = False
            return jpeg, seq


class FrameOrderGuard:
    """Never paint a picture older than the one on screen.

    A pane can receive frames from more than one path in a row (the lane
    PC's SDK host, then the Site Server relay after a fallback, or a server
    cache that briefly mixed a snapshot into a stream). Two rules:

    - a frame carrying a source sequence lower than the last painted one
      from the same source is old;
    - a frame whose bytes match a picture painted a few frames ago (but not
      the current one) is an old picture coming back.
    """

    def __init__(self, memory=16, *, clock=None):
        import time

        self._memory = max(2, int(memory))
        self._recent = []
        self._current = None
        self._seq = {}
        self._clock = clock or time.monotonic
        self._refusing_since = None

    def reset(self):
        self._recent.clear()
        self._current = None
        self._seq.clear()
        self._refusing_since = None

    # Refusing every frame for this long means the source started over
    # (restarted host, new decoder) with a low frame number, not that old
    # frames keep arriving: start again from the next frame.
    STUCK_SECONDS = 2.0

    # A camera frame number that drops by more than this is a restarted
    # source (HVX host restart, new decoder), not an older frame.
    RESET_GAP = 300

    def accept(self, jpeg, *, source="", seq=None):
        if not jpeg:
            return False
        if seq is not None:
            last = self._seq.get(source)
            if last is not None and int(seq) <= last and (last - int(seq)) < self.RESET_GAP:
                now = self._clock()
                if self._refusing_since is None:
                    self._refusing_since = now
                if now - self._refusing_since < self.STUCK_SECONDS:
                    return False
                self.reset()             # source restarted: follow its new numbering
        self._refusing_since = None
        key = hash(jpeg)
        if key == self._current:
            return False                 # same picture: nothing to repaint
        if key in self._recent:
            return False                 # an older picture coming back
        if seq is not None:
            self._seq[source] = int(seq)
        if self._current is not None:
            self._recent.append(self._current)
            if len(self._recent) > self._memory:
                del self._recent[0]
        self._current = key
        return True


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
