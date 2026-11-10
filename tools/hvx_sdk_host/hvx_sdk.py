"""Compatibility shim for the split HVX SDK implementation.

The vendor contract remains: Net_QueryConnState, Net_StartVideo,
Net_RegImageRecvEx2, and Net_SetDrawDataOut are bound by the implementation.
The video worker remains ``_camera_video_loop`` and ``_ensure_camera_pump`` in
the video subsystem; it retains ``hvx-live-`` and ``hvx-play-ui`` thread names
and the ``control_duration_ms`` diagnostic field.

Packaging compatibility markers (implemented in ``hvx_sdk_parts/40_video.py``):
``_get_native_jpg_buffer``, ``_native_jpeg_disabled_until``,
``draw_data_primary=draw_data_rc``, ``consumer_demand_age_ms``,
``pump_last_iteration_age_ms``, and ``callback_fps``.
"""

import sys as _sys

try:
    from tools.hvx_sdk_host import hvx_sdk_parts as _impl
except ModuleNotFoundError:  # direct ``python hvx_host.py`` execution
    import hvx_sdk_parts as _impl

_sys.modules[__name__] = _impl
