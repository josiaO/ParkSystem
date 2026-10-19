from unittest.mock import patch

from app.infrastructure.media.diagnostics import DEGRADED, FAIL, summarize_samples, verdict_for
from tools import camera_lab


def test_lab_reports_native_transport_without_inventing_decoded_frames():
    body = {"cameras": [{"camera_id": 7, "source": "sdk"}], "mediamtx_paths": {
        "cam7": {"ready": True, "bytes_received": 100, "codec": "H264"},
        "cam7_detect": {"ready": True, "bytes_received": 20},
        "cam8": {"ready": True, "bytes_received": 100},
    }}
    with patch.object(camera_lab, "get_json", return_value=body):
        rows, _ = camera_lab.sample_running("http://localhost", "token", 7)
    assert len(rows) == 1
    assert rows[0]["source"] == "mediamtx"
    summary = summarize_samples([rows[0], {**rows[0], "bytes_received": 200}])
    assert summary["frames_changed"] == 0
    assert summary["bytes_received"] == 100
    assert verdict_for(summary, duration_s=30)[0] == DEGRADED


def test_lab_rejects_stalled_native_transport():
    sample = {"measurement": "transport", "connection_state": "STREAMING", "bytes_received": 100}
    summary = summarize_samples([sample, sample])
    assert verdict_for(summary, duration_s=30)[0] == FAIL
