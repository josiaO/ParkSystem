"""Phase 4.1: camera lab `measure` helpers."""

from __future__ import annotations

from tools.camera_lab_replay import _variant_filter, char_accuracy, summarize_measure


def test_char_accuracy():
    assert char_accuracy("T123ABC", "T123ABC") == 1.0
    assert round(char_accuracy("T123A8C", "T123ABC"), 3) == round(1 - 1 / 7, 3)
    assert char_accuracy("", "T123ABC") == 0.0
    assert char_accuracy("T123ABC", "") == 0.0


def test_summary_counts_widths_reads_and_labels():
    rows = [
        {"variant": "production", "plate_width_px": 50, "plate": "T123A8C", "truth": "T123ABC", "ocr_ms": 10, "detector_ms": 40},
        {"variant": "production", "plate_width_px": 120, "plate": "T555XYZ", "truth": "T555XYZ", "ocr_ms": 12, "detector_ms": 41},
        {"variant": "production", "plate_width_px": None, "plate": "", "truth": "UNLABELED", "detector_ms": 39},
        {"variant": "full_resolution", "plate_width_px": 100, "plate": "", "truth": "T123ABC", "detector_ms": 60},
    ]
    summary = summarize_measure(rows, min_width=64)
    production = summary["production"]
    assert production["frames"] == 3 and production["plate_detected"] == 2
    assert production["below_min_width"] == 1 and production["read_rate"] == 1.0
    assert production["labelled_frames"] == 2 and production["exact_match_rate"] == 0.5
    assert production["char_accuracy"] == round((1 - 1 / 7 + 1) / 2, 3)
    assert summary["full_resolution"]["read_rate"] == 0.0


def test_production_variant_matches_the_worker_decoder():
    args, roi = _variant_filter("production", (0.06, 0.18, 0.94, 0.92))
    assert args == ["-vf", "scale=960:-2", "-q:v", "8"] and roi is None
    args, roi = _variant_filter("roi_before_scale", (0.06, 0.18, 0.94, 0.92))
    assert args[1].startswith("crop=") and "scale='min(960,iw)':-2" in args[1] and roi == "off"


# Phase 4.3: frame age at consumption ---------------------------------------

def test_lane_reports_frame_age_at_consumption_and_alarms_over_budget():
    from app.services.recognition_runtime import CameraRecognitionLane

    lane = CameraRecognitionLane(camera_id=5)
    sample = lane.offer_frame(b"\xff\xd8a\xff\xd9", source="test")
    lane.begin(lane.take_pending(), now=sample.received_at + 0.050)
    lane.inflight = None
    snap = lane.snapshot(now=sample.received_at + 0.1)
    assert snap["frame_age_at_consumption_ms"] == 50.0
    assert snap["frame_age_alarm"] is False

    for _ in range(5):
        sample = lane.offer_frame(b"\xff\xd8b\xff\xd9", source="test")
        lane.begin(lane.take_pending(), now=sample.received_at + 0.450)
        lane.inflight = None
    snap = lane.snapshot()
    assert snap["frame_age_at_consumption_ms_p95"] >= 300
    assert snap["frame_age_alarm"] is True


def test_desktop_health_mentions_old_frames():
    from app.desktop.desk import health_sentences

    text = health_sentences({"status": "ok", "recognition_runtime": {"cameras": [
        {"camera_id": 3, "frame_age_alarm": True, "frame_age_at_consumption_ms_p95": 820.0}]}})
    assert "camera 3" in text.lower() and "820" in text


# Phase 4.2: per-camera recognition decode width ----------------------------

def test_detect_width_defaults_to_site_setting_and_is_per_camera():
    from app.config import settings
    from app.services.camera_framing import apply_framing, framing_from_profiles

    assert settings.recognition_detect_width == 960
    assert framing_from_profiles({})["detect_width"] == 960
    profiles = apply_framing({}, detect_roi="", detect_zoom=1.0, detect_width=1920)
    assert framing_from_profiles(profiles)["detect_width"] == 1920
    # Saving the zone again without a width keeps the chosen width.
    again = apply_framing(profiles, detect_roi="off", detect_zoom=1.0)
    assert framing_from_profiles(again)["detect_width"] == 1920


def test_detect_width_rejects_odd_values():
    import pytest

    from app.services.camera_framing import apply_framing

    with pytest.raises(ValueError):
        apply_framing({}, detect_roi="", detect_zoom=1.0, detect_width=1000)


def test_worker_decoder_uses_the_camera_detect_width():
    from app.services.recognition_decoder import decoder_command

    command = decoder_command("rtsp://127.0.0.1:8554/cam1_detect", sample_fps=3, scale=1920)
    assert command[command.index("-vf") + 1] == "scale=1920:-2"
    source = open("app/recognition_worker/30_camera_worker.py", encoding="utf-8").read()
    assert 'scale=detect_width' in source
