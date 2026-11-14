# Recognition path measurements

## How the worker sees a plate

The recognition worker reads the local MediaMTX DETECT path with FFmpeg,
scales it to the camera's **detect width** (default 960 px), encodes JPEG
(`-q:v 8`), then FastALPR applies the detection zone, finds the plate and
reads its crop. The display stream is separate and is not affected by any
setting below.

## Measure (repeat for each camera's footage)

```bash
python -m tools.camera_lab_replay measure --dataset TestingData            # every image and video
python -m tools.camera_lab_replay measure "Video Project.mp4" --video-fps 2 --roi 0.06,0.18,0.94,0.92
```

The report (`TestingData/results/measure/measure-summary.json`) compares four
decode variants (production 960 px, ROI cropped before scaling, 1280 px, full
resolution): detection rate, plate width at the OCR input, how many plates fall
under `alpr_min_capture_plate_width_px` (64), read rate, OCR/detector time, and
accuracy against labels.

### Labels (needed for accuracy)

Accuracy needs human-checked plates in `TestingData/ground_truth.json`. Never
copy OCR output into it.

```json
{
  "images": {"I0105082026001435.jpg": "T659DCE"},
  "video": [{"file": "Video Project.mp4", "start": 9.0, "end": 12.0, "plate": "T279EFY"}]
}
```

## First results (2026-11-15, this repository's TestingData, one camera)

30 stills at the stop line and a 3-minute 1080p30 approach video sampled at 2 fps;
site detection zone `0.06,0.18,0.94,0.92`; no labels yet.

| Variant | Plate detected | Plate width p10 / p50 / p90 (px) | Under 64 px | Read rate | OCR ms p50 |
|---|---|---|---|---|---|
| production (960 px) | 38% | 27 / 43 / 132 | 106 of 148 | 82% | 14 |
| ROI cropped before scaling | 42% | 26 / 44 / 138 | 112 | 76% | 14 |
| 1280 px | 43% | 29 / 50 / 143 | 109 | 77% | 20 |
| full resolution | 42% | 44 / 72 / 234 | 62 | 89% | 41 |

* At the stop line plates are 118-208 px wide in production, well above 64 px.
  The small plates are approach frames; the arrival gate already waits for the
  car to come closer before reading.
* Cropping the zone before scaling gains little because the zone is 88% of the
  frame width. It would help only with a much narrower per-camera zone.
* Production and full-resolution reads disagree on 57 of 108 frames read by
  both, including stills with 118 px plates. Downscaling plus JPEG quality 8
  changes OCR results; which one is right needs labels.

## Changing a camera's detect width

`PUT /cameras/{id}/framing` with `{"detect_roi": "", "detect_zoom": 1.0, "detect_width": 1280}`
(allowed: 960, 1280, 1600, 1920). The site default is `SMARTPARK_RECOGNITION_DETECT_WIDTH`
(960). Change it only after labelled accuracy improves, and watch System Health:
wider decodes cost CPU (full resolution roughly triples OCR time) and raise frame
age; the worker raises `frame_age_alarm` when the p95 frame age at recognition
exceeds 300 ms.

## ONNX threads

Each ONNX session uses `recognition_model_threads` threads, or automatically
`min(2, (CPU cores - 1) // recognition_max_concurrency)` with
`recognition_max_concurrency = 4`: one thread per inference on 4-8 cores, up to
four inferences at once per process. Two processes can load the models (the
worker, and the Site Service for HVX software verification), so the worst case is
about eight inference threads plus one FFmpeg decoder per camera. Check CPU in
Task Manager under a four-camera load before raising anything; consider a GPU
provider only if the frame-age alarm fires while CPU is saturated.
