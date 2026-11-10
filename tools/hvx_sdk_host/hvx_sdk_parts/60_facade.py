from __future__ import annotations

class HVXSDK(_HVXConnectionMixin, _HVXCaptureMixin, _HVXVideoMixin, _HVXGPIOMixin):
    """Stable SDK facade composed from connection, capture, video and GPIO subsystems."""
