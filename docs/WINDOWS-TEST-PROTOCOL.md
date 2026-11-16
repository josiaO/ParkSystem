# Windows test protocol: stale display, stale recognition, slow boom

This is the procedure for the Windows rig (the PC with the HVX/QY cameras and
the boom). Nothing here can be measured on Ubuntu, because the camera SDK is a
32-bit Windows DLL. Each run writes one folder and one zip. Send the zip back.
Do not edit the scripts.

**Safety.** Runs A1 and B1 **physically open the boom** several times. Keep
the lane clear and have someone watching it. The script lists the cameras and
asks you to type `OPEN` before the first pulse.

## 0. Update and restart (once, before any run)

In PowerShell, in the checkout folder:

```powershell
git pull
```

Restart everything, so the instrumented code is running. If SmartPark runs
as Windows services:

```powershell
Restart-Service SmartParkHvxHost, SmartParkSiteService, SmartParkMediaService, SmartParkRecognitionWorker
```

If you start it with `scripts\Start-SmartPark.ps1` instead, close all the
SmartPark windows (including the 32-bit HVX host window) and start it again.

Check that the new host is running. This must print a list of histograms, not
an error:

```powershell
(Invoke-RestMethod http://127.0.0.1:8765/metrics).histograms_ms | Format-List
```

Check that the trace files appear (one per process):

```powershell
Get-ChildItem "$env:PROGRAMDATA\SmartParkEdge\logs\latency-trace-*.jsonl"
```

You should see `latency-trace-hvx-host.jsonl` and, once a camera is live,
`latency-trace-site-service.jsonl`, `latency-trace-recognition-worker.jsonl`
and `latency-trace-media-service.jsonl`. If a process is missing its file, that
process is still running the old code. Restart it.

Tracing is on by default and costs very little: one record per boom command,
per plate event and per decision, plus about one frame record per camera per
second. To switch it off later, set `SMARTPARK_LATENCY_TRACE=0` for the
services.

## A1. Boom timing, with and without live viewers (opens the boom)

This separates the software path (app → HTTP → host → SDK → relay command)
from everything else, under three loads: no extra viewers, four live viewers
per camera, and (A3) a saturated host.

Run it **twice**:

1. **Desktop app open**, showing the live video of all lanes, as an operator
   would have it.
2. **Desktop app closed** (services still running).

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -Beep
```

The script lists the connected cameras. If more than one is connected, it
stops and asks for the camera wired to the test boom. Run it again with that
handle, for example:

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -Beep -Handle 1
```

It takes about 3 minutes: 5 pulses with no extra viewers, then 5 pulses with
4 viewers per camera, 10 s apart. Each pulse prints its local time and a
"relay_on_after" figure, which is the software time from the command to the
SDK relay call.

**Send back:** both zips (they are on your Desktop under `SmartParkLatency`),
and say which one had the desktop app open.

## A2. Recognition and display staleness (does not open the boom by script)

This records real cars through the normal app: native camera events, worker
reads, decisions and the age of the frame or event each decision used, plus
the live-view frame age.

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -NoPulse -PassiveSeconds 900
```

During the 15 minutes, drive at least 10 passes through the lane(s). Include:

- two cars **back to back** (the second one close behind the first), at least
  twice. This is the case where an old image can be attached to a new car;
- one pass where you **stop for 20 s** under the camera before moving;
- one pass at the speed of a normal customer.

Write down each pass: time, plate, lane, and anything that looked wrong
(wrong plate, an old picture, a frozen live view and for how long, the boom
slow). The times printed on the PC clock are fine.

**Send back:** the zip and your list of passes.

## A3. Saturated host (optional, opens the boom)

This is the upper bound for hypothesis H1: every host HTTP worker held by an
idle keep-alive connection while a boom command arrives. On Ubuntu with the
fake SDK, the command waited about 8 s and the client gave up. The host then
still pulsed the relay, after the app had recorded a failure. This run checks
whether the real host does the same.

During this run other SmartPark requests to the host can fail for about a
minute and **the boom may open late**. Keep the lane clear.

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -Saturate -Pulses 3 -Handle 1
```

**Send back:** the zip, and whether the boom opened late (seconds after the
"pulse" line printed) or not at all.

## B. Physical boom movement (Phase B)

Software timestamps stop when the SDK accepts the relay command. They do not
show when the boom starts moving. Pick the method(s) you can do (see the
questions at the end). Each one gives a number per pulse that the software
trace cannot.

### B1. Phone slow-motion video with the beep (recommended)

Run A1 with `-Beep` (as above). The PC beeps just before each command is sent,
and the trace records the beep time.

1. Put the phone where it sees the **boom arm** and can **hear the PC
   speaker**. If the camera's relay click is audible, put the phone close
   enough to hear it too.
2. Record in slow motion (120 or 240 fps) through the whole run.
3. For each pulse, note in the video:
   - `t_beep`: the frame where the beep starts;
   - `t_click`: the frame of the relay click, if you can hear it;
   - `t_move`: the first frame where the boom arm moves.

**Send back:** for each pulse, the three frame numbers and the phone's frame
rate (or the video files, if that is easier).

How this is used: `t_click - t_beep` is software plus camera relay;
`t_move - t_click` is the boom controller itself (hypothesis H5). The trace
gives the software part exactly, so the difference is the camera and the
controller.

### B2. Read the boom's state through a camera input (if it is wired)

If the boom controller has an "open" or limit-switch output wired to one of
the camera's GPIO inputs, the host can log the edge to the millisecond.

First find which input changes. With the boom **closed**:

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/gpio-scan/1" | ConvertTo-Json -Depth 4
```

Then open the boom (with its remote or by hand) and run the same command
again while it is **open**. Replace `1` with the camera handle. An input whose
`value` differs between the two is the one to use. Then run A1 with polling on
that input, for example index 2:

```powershell
powershell -ExecutionPolicy Bypass -File tools\windows\Run-LatencyCapture.ps1 -Beep -Handle 1 -PollInput 2
```

**Send back:** the two `gpio-scan` outputs and the zip. If no input changes,
say so; then B1 is the only physical measurement.

## What is in the zip

| File | What it is |
|---|---|
| `report.txt` / `report.json` | `tools/latency_report.py` output: per stage p50/p95/p99/max, one row per boom command, stale counts, worst 10 with full traces |
| `latency-trace-latency-capture.jsonl` | the capture script's own trace (pulses, phases, beeps) |
| `logs/*latency-trace-*.jsonl` | host, Site Service, worker and media traces written during the run |
| `logs/*.log.tail.txt` | the last 4000 lines of each SmartPark log |
| `metrics.jsonl`, `metrics-before.json`, `metrics-after.json` | host `/metrics` every 2 s: HTTP queue wait, busy workers, rejections, callback time, heartbeat lag, capture mode |
| `viewers.csv` | every live frame the scripted viewers received, with its age |
| `pulses.csv` | each pulse with its local time (to line up with phone video) |
| `counters.csv`, `processes.csv` | CPU, memory, disk, run queue, and per-process CPU (python, ffmpeg, mediamtx, Defender) |
| `system.json` | Windows version, CPU, RAM, power plan, Defender real-time state, service states, git commit |
| `capture.json` | arguments, host `/info` and `/video-status` at start and end |
| `console.txt` | everything the script printed |

None of these files contain camera passwords. They do contain camera IP
addresses and the plates read during the run.

## Reading the report yourself (optional)

```powershell
python tools\latency_report.py "$env:USERPROFILE\Desktop\SmartParkLatency\capture-<date>-<time>"
```

Section 2 has one row per boom command:

| Column | Meaning | Hypothesis |
|---|---|---|
| `cmd>send` | command created → HTTP request sent (includes creating the HTTP client) | client cost |
| `hostQ` | the request waited for a free host worker | H1 |
| `send>host` | request sent → host handler started | H1, H7 |
| `host>sdk` | host handler → first SDK call | H8 |
| `sdk>relay` | `Net_GateSetup` + `Net_WriteGPIOState` | SDK / camera |
| `CMD>RELAY` | total software time to the relay command | H1 + H4 (scripted pulses skip H4) |
| `relay>resp` | relay command → response back in the app (includes the 500 ms hold) | |
| `board+` | how long after the GPIO call started the Board* relay was commanded | sites with a Board* relay |

`host: scheduling stall` in section 4 is the host's heartbeat thread waking
late (GIL held or CPU starved: H7/H8). `display: frame age` is how old the
picture was when a viewer got it (H2, H3, H6). `recognition: decision source
age` is how old the frame or native event behind each parking decision was
(H4, H6).
