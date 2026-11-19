"""The live camera picture never goes back in time.

Field report: the camera's on-screen clock ran 1, 2, 3, 4, 3, 4, 5. An older
frame was painted after a newer one because more than one path could write a
camera's live picture (stream producer, one-shot snapshots, the lane PC's SDK
host and the server relay). These tests pin both guards: the media gateway's
LIVE buffer (what every viewer reads) and the desktop pane's paint guard.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.desktop.frame_mailbox import FrameOrderGuard
from app.services.media_gateway import LocalMediaGateway


def frame(second: int) -> bytes:
    """A JPEG-shaped frame whose OSD clock shows ``second``."""
    return b"\xff\xd8" + f"OSD 12:00:{second:02d}".encode() + b"\xff\xd9"


def clock(sample) -> int:
    return int(sample.jpeg[2:-2].decode().rsplit(":", 1)[1])


class GatewayLiveOrderTests(unittest.TestCase):
    def setUp(self):
        self.gw = LocalMediaGateway()

    def test_late_frame_with_lower_source_sequence_is_not_shown(self):
        for second in (1, 2, 3, 4):
            self.gw.publish(5, frame(second), source="sdk", source_seq=second, detect=False)
        # A late reply (or a second reader of the same source) delivers 3.
        result = self.gw.publish(5, frame(3), source="sdk", source_seq=3, detect=False)
        self.assertIsNotNone(result, "a late frame must not stop a healthy producer")
        self.assertEqual(clock(self.gw.peek_live(5)), 4)
        self.gw.publish(5, frame(5), source="sdk", source_seq=5, detect=False)
        self.assertEqual(clock(self.gw.peek_live(5)), 5)
        self.assertEqual(self.gw.session(5).frames_out_of_order, 1)

    def test_one_shot_snapshot_does_not_interleave_with_running_stream(self):
        shown = []
        for second in (1, 2, 3, 4):
            self.gw.publish(6, frame(second), source="rtsp", source_seq=second, detect=False)
            shown.append(clock(self.gw.peek_live(6)))
            if second == 4:
                # Manual plate read / connect probe grabs a frame through a
                # slower path: it shows 3 while the stream already shows 4.
                self.gw.publish(6, frame(3), source="snapshot", detect=False)
                shown.append(clock(self.gw.peek_live(6)))
        self.gw.publish(6, frame(5), source="rtsp", source_seq=5, detect=False)
        shown.append(clock(self.gw.peek_live(6)))
        self.assertEqual(shown, sorted(shown), f"clock went backwards: {shown}")

    def test_one_shot_snapshot_is_used_when_no_stream_is_running(self):
        self.gw.publish(7, frame(9), source="snapshot", detect=False)
        self.assertEqual(clock(self.gw.peek_live(7)), 9)
        # A stream that went quiet long ago no longer blocks snapshots.
        self.gw.publish(7, frame(10), source="rtsp", source_seq=1, detect=False)
        self.gw.session(7).live_sequenced_at = time.monotonic() - 60
        self.gw.publish(7, frame(11), source="snapshot", detect=False)
        self.assertEqual(clock(self.gw.peek_live(7)), 11)

    def test_restarted_source_with_much_lower_sequence_is_accepted(self):
        self.gw.publish(8, frame(1), source="sdk", source_seq=5000, detect=False)
        self.gw.publish(8, frame(2), source="sdk", source_seq=1, detect=False)
        self.assertEqual(clock(self.gw.peek_live(8)), 2)

    def test_generation_change_resets_the_order(self):
        self.gw.publish(9, frame(1), source="sdk", source_seq=40, detect=False)
        row = self.gw.session(9)
        self.gw._invalidate_generation(row, "test")
        self.gw.publish(9, frame(2), source="rtsp", source_seq=1, generation=row.generation, detect=False)
        self.assertEqual(clock(self.gw.peek_live(9)), 2)


class PaneFrameOrderTests(unittest.TestCase):
    def paint(self, guard, frames):
        return [int(f[2:-2].decode().rsplit(":", 1)[1]) for f in frames if guard.accept(f)]

    def test_old_picture_coming_back_is_not_painted(self):
        guard = FrameOrderGuard()
        frames = [frame(s) for s in (1, 2, 3, 4, 3, 4, 5)]
        self.assertEqual(self.paint(guard, frames), [1, 2, 3, 4, 5])

    def test_sequenced_frames_never_go_backwards(self):
        guard = FrameOrderGuard()
        self.assertTrue(guard.accept(frame(1), source="host", seq=10))
        self.assertFalse(guard.accept(b"\xff\xd8other\xff\xd9", source="host", seq=9))
        self.assertTrue(guard.accept(frame(2), source="host", seq=11))

    def test_reset_for_a_new_camera(self):
        guard = FrameOrderGuard()
        guard.accept(frame(1))
        guard.accept(frame(2))
        guard.reset()
        self.assertTrue(guard.accept(frame(1)))


if __name__ == "__main__":
    unittest.main()


class CrossPathOrderTests(unittest.TestCase):
    """Direct (HVX host) and relay frames carry the same camera frame number."""

    def test_relay_part_carries_camera_frame_number(self):
        try:
            from app.desktop.streams import pop_latest_mjpeg_with_seq
        except ImportError:
            self.skipTest("PySide6 not installed")
        from app.services.preview import _mjpeg_part

        buf = _mjpeg_part(frame(1), 41) + _mjpeg_part(frame(2), 42)
        jpeg, seq, rest = pop_latest_mjpeg_with_seq(buf)
        self.assertEqual((jpeg, seq, rest), (frame(2), 42, b""))
        jpeg, seq, _ = pop_latest_mjpeg_with_seq(_mjpeg_part(frame(3)))
        self.assertEqual((jpeg, seq), (frame(3), None))

    def test_switching_paths_never_shows_an_older_camera_frame(self):
        guard = FrameOrderGuard()
        shown = []
        # direct path 100..103, fallback to the relay which lags (101, 102),
        # then newer relay frames, then back to the direct path.
        arrivals = [(100, 0), (101, 1), (102, 2), (103, 3), (101, 1), (102, 2), (104, 4), (105, 5)]
        for seq, second in arrivals:
            # the relay re-encodes nothing, but make the bytes differ to prove
            # the frame number (not the byte check) is what refuses them
            data = frame(second) + (b"relay" if seq in (101, 102) and shown and shown[-1] >= 3 else b"")
            if guard.accept(data, source="camera", seq=seq):
                shown.append(second)
        self.assertEqual(shown, [0, 1, 2, 3, 4, 5])

    def test_restarted_host_sequence_is_accepted(self):
        guard = FrameOrderGuard()
        self.assertTrue(guard.accept(frame(1), source="camera", seq=90000))
        self.assertTrue(guard.accept(frame(2), source="camera", seq=3))
