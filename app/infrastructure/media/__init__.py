"""Media provider registry.

The rest of SmartPark asks this package for live/detect endpoints instead of
knowing whether a camera is currently served by the legacy local gateway or
the MediaMTX sidecar.
"""

from .registry import (  # noqa: F401
    get_detect_endpoint,
    get_evidence_endpoint,
    get_live_endpoint,
    mediamtx_detect_active,
    mediamtx_live_active,
    register_camera_source,
    unregister_camera_source,
)
from .service import MediaService, media  # noqa: F401
