# Field realtime stability — 2026-10-02

This pass treats the Windows four-camera soak as higher-value evidence than
green unit tests. The previous MediaMTX/WebRTC work remains the preferred
live path. This change bounds recognition, isolates cameras, clears stale
plates, and makes one physical visit create one `ParkingSession`.

## Root causes (field)

### Slow / heavy live video
HVX JPEG was polled at 20 Hz (`live_sdk_interval_seconds=0.05`) while FastALPR
also ran a second CLAHE detect pass on every empty scene. On four cameras that
saturated CPU and delayed decode. The UI could still say MediaMTX while the
browser had fallen back to MJPEG.

### Recognition stacking / one camera stops
`_local_alpr_ready()` marked the per-camera cooldown *before* the global OCR
cap was checked. A busy pair of cameras made the other two skip for 0.5 s
repeatedly. Hybrid HVX cameras also ran **continuous HVX live_jpeg FastALPR**
(`presence=True` on every poll) in addition to native callbacks. That SDK JPEG
poll is no longer on the OCR path. ParkWatch InALPR still applies: FastALPR
reads the capture/detect JPEG for every `FASTALPR_ONLY` and `HYBRID` lane,
including QY/HVX. `NATIVE_ONLY` is the only mode that skips software OCR.

### Old plate sticking
`_plate_payload` promoted `latest_for_camera` from the database into the live
lane. The worker rarely fed empty reads into `ConsensusTrack`, so a published
plate could sit through several following cars. The browser also reused
`resolved_plate` / `liveLastCars` after the server had cleared state.

### Phantom / default plate
No hardcoded production registration was found. The “fixed” plate was stale
live state: last_car, fusion, and native `last_capture` presented as current.

### Duplicate ParkingSession
Uniqueness was `(site_id, entry_event_id)` and a 2-second similar-plate timer.
Each OCR publish has a new `event_id`. Concurrent OCR variants
(`T285DQP` / `T285DOP`) could both pass the check-then-insert window.

## Architecture after the fix

```
Camera JPEG / HVX callback
  -> LatestFrameMailbox (depth 1, sequence + generation)
  -> FairInferenceScheduler (1 in-flight per camera, global cap)
  -> FastALPR or native event
  -> LaneVisit (IDLE…EVENT_PUBLISHED)
  -> EntryLaneController + parking_entry_claims
  -> one ParkingSession
```

Live video still consumes MediaMTX/WebRTC or the direct JPEG cache and never
waits on OCR.

## Field verification on Windows

1. Confirm the operator pane shows `MEDIAMTX_WEBRTC` (not `DIRECT_MJPEG`) when
   WebRTC actually connected. If it says MJPEG, fix firewall/UDP 8189 before
   tuning OCR.
2. Run for 8 minutes while cars use all four lanes:

```
python tools\field_realtime_report.py --minutes 8 --url http://127.0.0.1:8760
```

PASS/FAIL soak (USB kit):

```
powershell -ExecutionPolicy Bypass -File Run-FieldAcceptanceTest.ps1 -Minutes 8 -ExpectedCars 6
```

3. Watch `GET /health/realtime` for:
   - `pending_queue_depth` ≤ 1
   - `fps` / frame age on the negotiated live provider
   - `inference_ms_p50` / `p95` / `max`
   - `recognition_stalls` / `recognition_restarts` only on the affected camera
   - `reconnects` isolated to the camera that dropped
   - `vehicle_present=false` and empty `last_plate` when the lane is empty
   - `sessions_created` matching physical entries, not OCR flicker

## Windows field follow-up (2026-10-02)

Desktop `/live.mjpeg` no longer reads `response.text` on a streaming 409 (that
painted `Attempted to access streaming response content, without having called
'read()'` onto the panes). HVX desktop panes use the SDK JPEG pump; MediaMTX
stays the live fan-out for browsers. HVX FastALPR is event/coil JPEG only — no
idle-scene OCR and no extra detect FFmpeg. Displayed plate confidence is the
raw OCR score (a Tanzania T###XXX shape no longer adds 0.35, which showed as a
hardcoded 65%). `Run-FieldAcceptanceTest.ps1` is ASCII so Windows PowerShell
5.1 can parse `--password`.

Hardware-dependent: glass-to-glass WebRTC latency, HVX callback timing, and
ONNX milliseconds on the site CPU cannot be proven in this repository.

## One PC, one gate (development)

`ZX5188` is not a bundled plate. The host last capture was being replayed
when event drain failed, so a previous read stayed on the live pane. Drain no
longer replays `state()`. Live Gates lane preset now tells this Site Service
which gate's ENTRY+EXIT to recognize (`POST /runtime/recognition-scope`).
Other gates discard SDK events without FastALPR. Production nodes pin the
same way with `SMARTPARK_RECOGNITION_GATE_ID`.
