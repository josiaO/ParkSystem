# MEDIA Module

See [MODULE-REGISTRY.md](MODULE-REGISTRY.md) and [OVERVIEW.md](OVERVIEW.md).

Implementation lives under `app/domain/`, `app/services/`, and `app/infrastructure/` — working HVX/Media paths are preserved.

The acquisition surface is `app.infrastructure.media.MediaService`. MediaMTX routes RTSP to WebRTC for the browser and to a local RTSP path for recognition. The recognition decoder is `app/services/recognition_decoder.py`; it is not a second media gateway. HVX live video stays on the SDK JPEG pump (`Net_StartVideo` + `Net_GetJpgBuffer`). Check a live install with `python -m tools.camera_lab` before treating streaming as fixed. See [MEDIA-ARCHITECTURE.md](../MEDIA-ARCHITECTURE.md).
