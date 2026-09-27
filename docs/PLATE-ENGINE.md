# Plate engine

## Purpose

Read lane photos the way ParkWatch did, with an engine that can be retrained or replaced.

ParkWatch (`InALPR=ON` / `OutALPR=ON`) saved each entry and exit JPEG and sent it to SimpleLPR (`LPRHelper.RecognizeAll`) with `Country=Tanzania` and contrast `918`. The camera supplied the picture. The PC supplied the plate text.

SmartPark keeps that split. The HVX/QY camera still snaps the JPEG. **FastALPR** is the reader. Parking sees one plate event.

## What owns this

| Piece | Role |
|---|---|
| `app/infrastructure/recognition/engines/base.py` | `PlateEngine` contract |
| `app/infrastructure/recognition/engines/fastalpr.py` | FastALPR implementation (the known engine) |
| `app/infrastructure/recognition/engines/registry.py` | Which engine is active |
| `app/infrastructure/recognition/engines/training.py` | Correction log and model-pack install |
| `app/services/alpr.py` | Detect, crop, OCR, Tanzania profile |
| `app/services/ocr_policy.py` | `FASTALPR_ONLY` reads every presence JPEG |
| Desktop **Plate Engine** page | Status, model folder, apply a pack |

The engine id is `fastalpr`. Version string: `fastalpr-1`.

Models:

- Detector: `yolo-v9-t-384-license-plate-end2end` (`yolo-v9-t-384-license-plates-end2end.onnx`)
- OCR: `cct-xs-v2-global-model` (`cct_xs_v2_global.onnx` + `cct_xs_v2_global_plate_config.yaml`)

Country default is Tanzania. Contrast sensitivity default is `0.918` (ParkWatch `Contrast=918`).

## Flow

1. Camera connects (HVX port 30000, or RTSP/HTTP for a camera without that SDK).
2. A car triggers a JPEG (image callback, coil, or the detect frame).
3. `recognize_frame` sends that JPEG to the active engine.
4. FastALPR detects the plate, pads the crop, and OCRs the crop only.
5. The Tanzania profile fixes digit/letter positions on `T###XXX` plates.
6. Parking stores one normalized plate.

`NATIVE_ONLY` still exists for a lane that should keep the camera's own text. The site default is `FASTALPR_ONLY`.

## Retrain

1. When a reading is wrong, `POST /recognition/corrections` with `image_ref`, `predicted`, and `corrected`.
2. Rows append to `media/recognition/corrections.jsonl`.
3. Train a new detector ONNX and a new OCR ONNX + yaml outside this app.
4. Put them in a folder with `manifest.json`:

```json
{
  "engine_id": "fastalpr",
  "country": "Tanzania",
  "detector_onnx": "yolo-v9-t-384-license-plates-end2end.onnx",
  "ocr_onnx": "cct_xs_v2_global.onnx",
  "ocr_config": "cct_xs_v2_global_plate_config.yaml"
}
```

5. Apply the folder from the Plate Engine page, or `POST /recognition/model-pack` with `{"directory": "/path/to/pack"}`.
6. The loaded reader is dropped. The next car uses the new files.

## Replace the library

Implement `PlateEngine` (`id`, `display_name`, `version`, `describe`, `recognize_bytes`). `recognize_bytes` must return `ok`, `plates`, and `best` in the same shape as FastALPR. Call `register_engine(...)` and set `SMARTPARK_ALPR_ENGINE` to that id. Do not edit parking, gates, or the HVX host.

## Desktop

PySide6. `app/desktop/launch.py` starts the API and the window on Windows and Linux. The 32-bit HVX host starts only on Windows, because `NetSDK.dll` is a Windows library. Plate reading does not need that host when the JPEG comes from RTSP or HTTP.

## What this must not do

- Move or rewrite `tools/hvx_sdk_host/`, `app/services/hvx_client.py`, or `app/services/gates.py`
- Put OCR inside the live-view decoder
- Invent a plate when the engine finds none
