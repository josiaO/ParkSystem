from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LiveGatesUiTests(unittest.TestCase):
    def test_web_live_gates_has_dual_panes_and_ips_tab(self):
        html = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-page="cameras">Live Gates</button>', html)
        self.assertNotIn('data-page="lanes"', html)
        self.assertNotIn('id="page-lanes"', html)
        self.assertIn('id="cameras-sub-live"', html)
        self.assertIn('id="cameras-sub-ips"', html)
        self.assertIn('data-sub="ips">IPs</button>', html)
        self.assertIn('data-slot="0"', html)
        self.assertIn('data-slot="1"', html)
        self.assertIn("Capture snapshot", html)
        self.assertIn("Cropped plate", html)
        self.assertIn("Connect all", html)
        self.assertIn("Discover", html)
        self.assertIn("Onboard wizard", html)
        self.assertIn("Save site locale", html)
        self.assertIn('id="site-timezone"', html)
        self.assertIn('data-role="camera"', html)
        self.assertIn("Fill both from lane", html)
        self.assertIn("Choose camera", html)
        self.assertIn("/live/watch", html)
        self.assertIn("function startDualLive", html)
        self.assertIn("function pairLaneCameras", html)

    def test_desktop_live_gates_replaces_old_lanes_page(self):
        desktop = (ROOT / "app" / "desktop" / "main.py").read_text(encoding="utf-8")
        self.assertIn('add_page("Live Gates", Cameras)', desktop)
        self.assertNotIn('add_page("Cameras", Cameras)', desktop)
        self.assertNotIn('add_page("Live Gates", Lanes)', desktop)
        self.assertNotIn("class Lanes", desktop)
        self.assertIn("class CameraLivePane", desktop)
        self.assertIn('addTab(live, "Live")', desktop)
        self.assertIn('addTab(ips, "IPs")', desktop)
        self.assertIn("Choose camera", desktop)
        self.assertIn("Onboard wizard", desktop)
        self.assertIn("Fill both from lane", desktop)
        self.assertIn("showPopup", desktop)
        self.assertIn("pair_lane_cameras", desktop)
