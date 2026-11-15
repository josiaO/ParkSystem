# 72-hour soak test

Proves that a fully loaded gate PC runs for three days without leaking memory,
restarting decoders, falling behind on frames, or slowing gate commands. Run it
before go-live and after any change to the camera, recognition or media path.

`tools/soak_monitor.py` only reads health endpoints and the process list. It
never opens a gate.

## Setup

1. The PC is installed with Windows services (see WINDOWS-SERVICES.md) and the
   reboot test has passed.
2. All 4 cameras are connected, assigned to their gates and recognising plates.
   Live video for at least one camera is open in the desktop for the whole run
   (as an operator would have it).
3. Real traffic is best. Otherwise replay footage through the cameras' RTSP
   paths with `python -m tools.camera_lab_replay serve` so recognition is busy.
4. Windows Update active hours / restarts are paused for the test window.
5. Write down the PC model, CPU, RAM, Windows build and Zirp version.

## Run

On the gate PC (normal PowerShell, in the install folder):

```powershell
$env:SMARTPARK_PASSWORD = Read-Host "Admin password"
.\python64\python.exe -m tools.soak_monitor --hours 72 --interval 60 --out "$env:ProgramData\SmartParkEdge\soak"
```

Keep the window open (or run it as a scheduled task). `Ctrl+C` stops early and
still writes the summary. Samples go to `samples.jsonl`; the result to
`summary.md` and `summary.json` in the output folder.

During the run, at least once each:

* restart one camera (power) and check that only that camera recovers;
* stop `SmartParkMediaService` for a minute and start it again;
* drive real or replayed cars through every lane.

## Pass criteria

| Check | Pass |
|---|---|
| Memory growth | each process (Site Service, worker, Media Service, MediaMTX, FFmpeg, HVX host) grows by at most 5 MB/hour after the first hour |
| Decoder restarts | at most 3 per camera per day, apart from the deliberate interruptions above |
| Frame age | the median of each camera's p95 frame age at recognition stays at or under 300 ms |
| Gate commands | average latency at most 1000 ms; no failed commands |
| Database link | never DOWN |

Also check by hand: the Windows Event Viewer has no SmartPark service crashes,
disk use under `%ProgramData%\SmartParkEdge\media` stays within the retention
budget, and System Health shows no watchdog problems at the end.

Attach `summary.md`, the PC details and anything unusual to the site's
acceptance record. A FAIL is a finding to investigate, not a reason to rerun
until it passes.
