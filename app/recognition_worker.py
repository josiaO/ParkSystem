"""Compatibility marker for the split recognition-worker package.

The implementation remains importable as ``app.recognition_worker``. The
worker reads ``cam{id}_detect`` paths and calls ``publish_recognition``; its
idle cadence includes ``await asyncio.sleep(2.0)``.

The implementation is loaded from the split package and uses the local
``app.services.recognition_decoder`` MediaMTX consumer.
"""
