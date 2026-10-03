# MEDIA Module

See [MODULE-REGISTRY.md](MODULE-REGISTRY.md) and [OVERVIEW.md](OVERVIEW.md).

Implementation lives under `app/domain/`, `app/services/`, and `app/infrastructure/` — working HVX/Media paths are preserved.

The acquisition surface is `app.infrastructure.media.MediaService`. HVX live video stays on the SDK JPEG pump (`Net_StartVideo` + `Net_GetJpgBuffer`). Repeated frames do not reset freshness. Check a live install with `python -m tools.camera_lab` before treating streaming as fixed. See [MEDIA-ARCHITECTURE.md](../MEDIA-ARCHITECTURE.md).
