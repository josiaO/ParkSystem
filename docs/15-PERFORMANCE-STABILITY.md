# Performance and stability

## Purpose

Keep SmartPark running on the Windows parking PC without freezing the UI, decoding unused video, or dying when one camera or the HVX host fails.

## What owns this

- Process split: `app/site_service.py` (API), `app/desktop/launch.py` (UI client), `tools/hvx_sdk_host/` (32-bit NetSDK)
- Health: `app/services/health.py`, `/health/live`, `/health/ready`, `/health/details`
- Live video: `app/services/preview.py` viewer count + idle stop
- Native ALPR first: `app/services/ocr_policy.py` (`NATIVE_ONLY` default)
- Queues / backoff: `app/services/queues.py`, `app/services/circuit.py`
- Windows tasks: the installer runs `packaging/windows/Install-SmartParkServices.ps1` and starts Site Service + HVX host at logon

## Live video design

Live view shares one SDK JPEG pump (`Net_GetJpgBuffer` via the host) and stops decoding when Cameras is hidden. Live Gates shows the car snapshot from the plate callback, not four RTSP decoders. FastALPR is not run on every frame.

## What it must NOT do

- Load `NetSDK.dll` in the 64-bit UI or Site Service
- Run FastALPR continuously on all four streams
- Start live pumps at Connect all
- Hold a DB session open during GPIO or MJPEG
- Use `uvicorn --reload` on the site PC

## Request / event flow

1. Site Service reports `READY_CORE` after schema/bootstrap; HVX connects asynchronously
2. Plate callback → bounded persist → short session/gate path → outbox retry if the gate step fails
3. UI opens `/live.mjpeg` → `acquire_live` → shared pump; leaving the page `release_live`; idle timeout stops decode

## Tests

`tests/test_stability.py`, live-view and Windows packaging tests.

## How to extend safely

Measure with `/health/details` before adding workers. Default `adapter_id` stays `hvx`.
