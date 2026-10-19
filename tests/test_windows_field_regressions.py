import io
import json
import pytest
from unittest.mock import patch

from app.services import mediamtx


def test_image_response_keeps_one_generation_when_file_is_replaced(tmp_path):
    from app.api_main import serve_media

    path = tmp_path / "live-4.jpg"
    path.write_bytes(b"first image")
    with patch("app.api_main.media_path", return_value=path):
        response = serve_media("crops", path.name, None)
    path.write_bytes(b"a different and much longer image")
    assert response.body == b"first image"
    assert int(response.headers["content-length"]) == len(response.body)
    assert response.headers["cache-control"] == "no-store"


def test_media_owner_repairs_missing_lane_paths_and_removes_old_lane():
    body = io.BytesIO(json.dumps({"items": [{"name": "cam1", "source": "rtsp://old/video"}]}).encode())
    with patch.object(mediamtx, "_sources", {3: {"uri": "rtsp://lane2/video"}}), \
         patch("urllib.request.build_opener") as opener, \
         patch.object(mediamtx, "_upsert_path", return_value=200) as upsert, \
         patch.object(mediamtx, "_control_api", return_value=200) as control:
        opener.return_value.open.return_value = body
        assert mediamtx.reconcile_paths()
    assert upsert.call_args.args[:2] == ("cam3", "rtsp://lane2/video")
    control.assert_called_once_with("DELETE", "/v3/config/paths/delete/cam1")


def test_superseded_crop_cannot_be_served_under_previous_plate_version(tmp_path):
    from fastapi import HTTPException
    from app.api_main import serve_media

    path = tmp_path / "live-4.jpg"
    path.write_bytes(b"next car")
    with patch("app.api_main.media_path", return_value=path), pytest.raises(HTTPException) as error:
        serve_media("crops", path.name, None, "old-version")
    assert error.value.status_code == 410


def test_reconciliation_does_not_restart_unchanged_stream():
    body = io.BytesIO(json.dumps({"items": [{"name": "cam3", "source": "rtsp://lane2/video", "sourceOnDemand": False, "rtspTransport": "tcp"}]}).encode())
    with patch.object(mediamtx, "_sources", {3: {"uri": "rtsp://lane2/video"}}), \
         patch("urllib.request.build_opener") as opener, \
         patch.object(mediamtx, "_upsert_path") as upsert:
        opener.return_value.open.return_value = body
        assert mediamtx.reconcile_paths()
    upsert.assert_not_called()


def test_decoder_allows_h264_parameter_set_discovery():
    from app.services.recognition_decoder import decoder_command

    with patch("app.services.recognition_decoder.ffmpeg_bin", return_value="ffmpeg"):
        command = decoder_command("rtsp://127.0.0.1:8554/cam3", sample_fps=4)
    assert int(command[command.index("-probesize") + 1]) >= 1000000
    assert "nobuffer+discardcorrupt" not in command
