# Performance and stability

## Purpose

Keep SmartPark running on the Windows parking PC without freezing the UI, decoding unused video, or dying when one camera or the HVX host fails.

## What owns this

- Process split: `app/site_service.py` (API), `app/desktop/launch.py` (UI client), `tools/hvx_sdk_host/` (32-bit NetSDK)
- Health: `app/services/health.py`, `/health/live`, `/health/ready`, `/health/details`
- Live video: `app/services/media_gateway.py` one producer per camera; `app/services/preview.py` is the live-view consumer
- Native ALPR first: `app/services/ocr_policy.py` (`NATIVE_ONLY` default)
- Queues / backoff: `app/services/queues.py`, `app/services/circuit.py`
- Windows tasks: the installer runs `packaging/windows/Install-SmartParkServices.ps1` and starts Site Service + HVX host at logon

## Live video design

Live view shares one MediaGateway producer per camera. HVX uses the host JPEG pump (`Net_GetJpgBuffer`); generic IP uses one FFmpeg process with a named profile (`LOW_LATENCY_LAN` with `COMPATIBLE` fallback). Both paths keep a **latest-frame** live buffer (max 1) and a separate detect buffer for FastALPR. The UI shows that latest frame; it does not play a backlog. **Live Gates** shows two cameras of a lane (entry and exit) with last-car snapshot, cropped plate, and read time under each pane. Discover, Connect all, and camera IPs are on the inner **IPs** tab. FastALPR runs on every **connected** lane (HVX callbacks, coil, or sampled detect frames) even if live view is closed. Opening a camera is view-only. Leaving Live Gates, switching to IPs, or hiding the window releases UI viewers; the producer stays up only if detect still needs it. Stream profiles (MAIN/SUB/LIVE/DETECT), codec, FPS, GOP, transport, and live/AI frame age are on **Live Gates → IPs → Stream profiles** and Hardware Lab.

## What it must NOT do

- Load `NetSDK.dll` in the 64-bit UI or Site Service
- Run FastALPR continuously on all four streams
- Start live pumps at Connect all
- Hold a DB session open during GPIO or MJPEG
- Use `uvicorn --reload` on the site PC

## Request / event flow

1. Site Service reports `READY_CORE` after schema/bootstrap; HVX connects asynchronously
2. Plate callback → bounded persist → short session/gate path → outbox retry if the gate step fails
3. UI opens `/live.mjpeg` → `acquire_live` → shared gateway producer; leaving the page `release_live`; idle timeout stops decode when detect does not need the source

## Tests

`tests/test_stability.py`, `tests/test_media_gateway.py`, live-view and Windows packaging tests.

## How to extend safely

Measure with `/health/details` before adding workers. Default `adapter_id` stays `hvx`.
