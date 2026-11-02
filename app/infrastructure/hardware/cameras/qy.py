"""QY camera adapter backed by the isolated OcxConfig/NetSDK host.

QY is intentionally a separate adapter identity even though it shares the
stable native implementation with the historical ``hvx`` alias.  This lets
future vendor SDKs add their own semantics without inheriting QY behavior.
"""

from __future__ import annotations

from app.services.hvx_client import HVXHostClient

from .hvx import HVXCameraAdapter


class QYCameraAdapter(HVXCameraAdapter):
    id = "qy"

    def __init__(self, client: HVXHostClient | None = None):
        super().__init__(client, adapter_id="qy")

