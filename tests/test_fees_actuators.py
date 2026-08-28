from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.db import is_postgres, is_sqlite
from app.services.board_tcp import FRAMES, frame_name_for, tw_frame
from app.services.fee_engine import CAR1_RULES, calculate_car1_fee
from app.services.led_udp import DEVICE_TYPE_UDP, PKC_NOTIFY, ROOT_PLAY, build_play_datagram, encode_led_text


class FeeEngineTests(unittest.TestCase):
    def test_grace_period_is_free(self):
        start = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=2700)
        result = calculate_car1_fee(start, end)
        self.assertEqual(result.due, 0)
        self.assertIn("grace", result.breakdown)

    def test_just_over_day_grace_charges_one_block_after_subtract(self):
        start = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=2701)
        result = calculate_car1_fee(start, end)
        self.assertEqual(result.due, 1000)
        self.assertIn("minus:1000", result.breakdown)

    def test_car1_constants_match_sql(self):
        self.assertEqual(CAR1_RULES["free_day_seconds"], 2700)
        self.assertEqual(CAR1_RULES["free_night_seconds"], 2100)
        self.assertEqual(CAR1_RULES["day_block_fee"], 1000)
        self.assertEqual(CAR1_RULES["daily_wrap_fee"], 34000)
        self.assertEqual(CAR1_RULES["day_start"], "05:05:00")


class ActuatorProtocolTests(unittest.TestCase):
    def test_board_stx_and_tw_frames(self):
        self.assertEqual(FRAMES["stx_open"], b"\x02\x31\x03")
        self.assertEqual(FRAMES["stx_close"], b"\x02\x32\x03")
        self.assertEqual(tw_frame(0x02, 1)[:2], b"\xAA\x55")
        self.assertEqual(len(tw_frame(0x02, 1)), 7)
        self.assertEqual(frame_name_for("open", "stx_open"), "stx_open")
        self.assertEqual(frame_name_for("open", "tw_open"), "tw_open")

    def test_led_datagram_uses_ledapi_constants(self):
        packet = build_play_datagram("WELCOME")
        self.assertGreaterEqual(len(packet), 32)
        self.assertLessEqual(len(packet), 512)
        self.assertEqual(packet[0], DEVICE_TYPE_UDP)
        # little-endian HHHH: device, notify, root
        self.assertEqual(int.from_bytes(packet[2:4], "little"), PKC_NOTIFY)
        self.assertEqual(int.from_bytes(packet[4:6], "little"), ROOT_PLAY)
        self.assertIn(encode_led_text("WELCOME"), packet)

    def test_sqlite_is_current_store(self):
        self.assertTrue(is_sqlite("sqlite:///tmp/smartpark.db"))
        self.assertTrue(is_postgres("postgresql+psycopg://u:p@localhost/smartpark"))
        self.assertFalse(is_sqlite("postgresql+psycopg://u:p@localhost/smartpark"))


if __name__ == "__main__":
    unittest.main()
