"""Compatibility marker for the split ``app.services.media_gateway`` package.

The HTTP still producer remains in the media gateway subsystem with
``interval = 0.2`` and deliberately does not use ``live_sdk_interval_seconds``.
"""

async def _http_stills():
    interval = 0.2
    await _sleep(interval)
