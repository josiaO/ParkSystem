"""Static checks for the canonical web UI product surface."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
DOCS = ROOT / "docs" / "ui"


class ProductUiTests(unittest.TestCase):
    def test_navigation_groups_and_role_gate(self):
        self.assertIn(">Overview</div>", HTML)
        self.assertIn(">Operations</div>", HTML)
        self.assertIn(">Management</div>", HTML)
        self.assertIn(">System</div>", HTML)
        self.assertIn('data-nav-id="plates"', HTML)
        self.assertIn('data-page="detections"', HTML)
        self.assertIn("Detections", HTML)
        self.assertIn("Testing &amp; Simulation", HTML)
        self.assertIn("function deploymentKind()", HTML)
        self.assertIn("function isTechnician()", HTML)
        self.assertIn("body:not(.role-tech) .tech-only", HTML)
        self.assertIn('id="sdk-disconnect"', HTML)
        self.assertIn("Disconnect this camera?", HTML)

    def test_operator_labels_hide_engine_names(self):
        self.assertIn("Use SmartPark AI recognition", HTML)
        self.assertIn("Use camera recognition", HTML)
        self.assertIn("Video only", HTML)
        self.assertIn(">Devices</button>", HTML)
        self.assertIn(">Test Video</button>", HTML)
        self.assertIn(">Discover Streams</button>", HTML)
        self.assertIn(">Test Recognition</button>", HTML)
        self.assertNotIn(">Probe RTSP</button>", HTML)
        self.assertNotIn(">NATIVE_ONLY</option>", HTML)
        self.assertIn("Plate Engine", HTML)  # mapped to Detections in the client

    def test_live_card_and_empty_states(self):
        self.assertIn('data-role="biz-camera"', HTML)
        self.assertIn('data-role="decision"', HTML)
        self.assertIn("No cameras configured.", HTML)
        self.assertIn("No detections yet.", HTML)
        self.assertIn("No watchlists configured.", HTML)
        self.assertIn("Check plate", HTML)
        self.assertIn('id="open-kiosk"', HTML)
        self.assertIn("SMARTPARK PAYMENT", HTML)

    def test_onboarding_uses_business_language(self):
        self.assertIn("What do you want to use this site for?", HTML)
        self.assertIn("US Dollar (USD)", HTML)
        self.assertIn("English", HTML)
        self.assertIn("1 entry / 1 exit", HTML)
        self.assertIn("Accept any format", HTML)
        self.assertIn("isTechnician()", HTML)

    def test_ui_docs_exist(self):
        for name in (
            "UI-ARCHITECTURE.md",
            "DESIGN-TOKENS.md",
            "NAVIGATION-MATRIX.md",
            "ROLE-MATRIX.md",
            "MODULE-UX-MATRIX.md",
            "SCREEN-SPECIFICATIONS.md",
            "UI-BACKEND-CONTRACT-GAPS.md",
            "UI-ACCEPTANCE-CHECKLIST.md",
        ):
            self.assertTrue((DOCS / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
