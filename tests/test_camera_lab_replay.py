from tools.camera_lab_replay import _recognition_diagnosis


def test_replay_diagnosis_distinguishes_latest_frame_skips_from_queue_stacking():
    result = _recognition_diagnosis([
        {"frame_seq_lag": 5, "completed_frame_age_ms": 1233},
        {"frame_seq_lag": 2, "completed_frame_age_ms": 900},
    ], True)

    assert result["lag_detected"] is True
    assert result["queue_depth"] == 0
    assert result["queue_stacking_detected"] is False
    assert result["failure_class"] == "recognition-slower-than-live"


def test_replay_diagnosis_passes_when_recognition_keeps_up():
    result = _recognition_diagnosis([
        {"frame_seq_lag": 0, "completed_frame_age_ms": 180},
        {"frame_seq_lag": 1, "completed_frame_age_ms": 250},
    ], True)

    assert result["lag_detected"] is False
    assert result["interpretation"] == "Recognition kept up with the live source."
