# SmartPark Camera Lab

The recorded-footage lab is available through the existing CLI entry point:

```bash
.venv/bin/python -m tools.camera_lab inspect TestingData
.venv/bin/python -m tools.camera_lab ground-truth --dataset TestingData
.venv/bin/python -m tools.camera_lab test-image --dataset TestingData
.venv/bin/python -m tools.camera_lab test-video --duration 60
.venv/bin/python -m tools.camera_lab test-video --duration 60 --recognition
.venv/bin/python -m tools.camera_lab multi-camera --duration 60 --recognition
.venv/bin/python -m tools.camera_lab failure-test --scenario stream-interruption
.venv/bin/python -m tools.camera_lab report TestingData/results
```

`serve` keeps one looping virtual camera alive for manual clients:

```bash
.venv/bin/python -m tools.camera_lab serve
```

It publishes the source with `ffmpeg -re -stream_loop -1` and stream-copies
the source H.264 video to a local MediaMTX path. The default endpoints are
`rtsp://127.0.0.1:8554/test-gate-entry` and the corresponding WHEP endpoint on
port 8889. `test-video` then consumes that RTSP path through the production
`LocalMediaGateway`, whose FFmpeg decoder fills the bounded live/latest-frame
buffers. Recognition-on runs the existing `app.services.alpr.recognize_bytes`
entry point against the newest buffer sample in a dry-run sink.

Generated inventory, JSON metrics, detection overlays, raw crops and prepared
OCR crops live under `TestingData/results/`. Raw `TestingData/` content is
ignored by Git and is never uploaded, renamed, recompressed or deleted.

The lab does not start Site Service, the parking event outbox, gate adapters,
receipt printers or payment providers. It therefore cannot prove physical HVX
SDK behavior or create parking sessions. It also reports recognition accuracy
only after a human edits `TestingData/ground_truth.json`; model output is not
accepted as truth.
