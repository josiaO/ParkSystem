"""Safe-migration flags. Current HVX + LocalMediaGateway stay authoritative."""

from __future__ import annotations

from typing import Any


LIVE_VIEW_DIRECT_LEGACY = "DIRECT_LEGACY"
LIVE_VIEW_MEDIAMTX = "MEDIAMTX"
RECOGNITION_FASTALPR_LEGACY = "FASTALPR_LEGACY"
RECOGNITION_FASTALPR_NEW = "FASTALPR_NEW"

DEFAULT_FLAGS: dict[str, Any] = {
    "media_gateway_enabled": False,
    "media_gateway_camera_ids": [],
    "fastalpr_new_pipeline_enabled": False,
    "webrtc_live_enabled": False,
    "native_alpr_enabled": True,
    "live_view_provider": LIVE_VIEW_DIRECT_LEGACY,
    "recognition_pipeline": RECOGNITION_FASTALPR_LEGACY,
}
