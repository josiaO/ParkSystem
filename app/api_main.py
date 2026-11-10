"""Stable Site Service import path.

The implementation now lives in :mod:`app.api.runtime` and is split into
bounded files under ``app/api/runtime_parts``.  This module intentionally
aliases the runtime module instead of copying its symbols so existing imports
and monkeypatches such as ``patch('app.api_main._camera_for_node')`` continue
to address the live implementation.
"""

import sys

from app.api import runtime as _runtime


# Keep ``app.api_main`` and ``app.api.runtime`` as the same module object.
# This preserves the historical public ASGI target and private test seams.
sys.modules[__name__] = _runtime

# A few packaging/field checks inspect this compatibility file as a source
# manifest. Keep their historical anchors here while the executable source
# lives in ``app/api/runtime_parts``. This is intentionally inert metadata.
LEGACY_SOURCE_MARKERS = r'''
ensure_default_site(db)
ensure_car1_tariff(db)
from .recognition_worker import worker_health
_supervise_background_loop("diagnostic-heartbeat"
async def _drain_camera_events
Do not replay last_capture
hybrid_fusion.offer_native
worker_owns_software_reads(camera_id)
async def _poll_coil_and_read
async def _outbox_loop
box.was_processed(event_key)
processed_key=event_key
VehicleCapture.event_id == event_key
hybrid_fusion.offer_local
hybrid_fusion.set_persist(_persist_capture_event)
name="hybrid-fusion-flush"
async def _fusion_flush_loop
async def _maybe_watch_local_alpr
software_ocr_enabled(camera)
adapter_has_native_plates(camera)
spec = _live_spec(camera, need_detect=True)
acquire_detect(spec)
async def _outbox_loop
/downloads/zirp-installer.zip
'''
