# Running a site: services, logs and recovery

## The services

On a Site Server or Edge Node, Zirp runs as Windows services. They start with
Windows, run with nobody signed in, and restart on their own if they crash
(after 5 s, then 15 s, then 60 s).

| Service | What it does | Port |
|---|---|---|
| `SmartParkSiteService` | API, parking decisions, payments, alerts, lane sweeper | TCP 8760 |
| `SmartParkMediaService` | Camera streams, live video (MediaMTX) | TCP 8889, UDP/TCP 8189 |
| `SmartParkRecognitionWorker` | Plate recognition (FastALPR) | — |
| `SmartParkHvxHost` | 32-bit QY/HVX camera SDK host (or a sign-in task) | 127.0.0.1:8765 |
| `SmartParkPortal` | Back office and driver pay page | TCP 3000 |
| `SmartParkCache` | Shared cache (Redis), camera PCs only, when the release bundles it | 127.0.0.1:6391 |

The shared cache holds short-lived lane state that the Site Service and the
Recognition Worker both need, such as how many times the car at each camera
has been read. It keeps nothing on disk and is not a record: PostgreSQL is.
If it's stopped, Zirp carries on with each process's own memory and picks the
cache up again a few seconds after it's back. Its settings file is
`config\redis.conf`, rewritten on every install.

Ground-loop boards talk to the Site Service on UDP 8000. The installer opens
the LAN firewall ports for the local subnet only.

## zirpctl

All of these run from an administrator PowerShell:

```powershell
$z = "C:\Program Files\Zirp\bin\zirpctl.ps1"
& $z status                      # installed versions, role, service state
& $z services restart            # stop and start everything in the right order
& $z services stop
& $z services start
& $z backup -Label manual        # database dump now
& $z rollback                    # back to the previous version
& $z rollback -RestoreDatabase   # ...and the database from before the update
```

Start menu shortcuts: **Zirp status and versions**, **Zirp logs** and **Zirp
startup check**.

## Is it healthy?

From any browser on the LAN:

| URL | Tells you |
|---|---|
| `http://<server>:8760/health/live` | The Site Service is up |
| `http://<server>:8760/health/ready` | It's ready to take traffic |
| `http://<server>:8760/health/database` | The database link is fine |
| `http://<server>:8760/health/pipeline` | Per camera: frame age, reconnects, recognition state |

## Logs

Everything is under `C:\ProgramData\SmartParkEdge\logs`:

| Folder | Contents |
|---|---|
| `logs\services\` | One log per service, rotated at 10 MB |
| `logs\install\` | Every install, update and rollback (`last-error.txt` explains a failed one) |

Lines worth searching for: `MANUAL OPEN` (barrier opened by hand), `ALERT`
(alert delivery), `stale` (old frames or events that were ignored on purpose)
and `RUNTIME` (heartbeat).

## Changing settings

Most settings are on screen in the desktop app, under **Settings**, and apply
without a restart:

| Tab | What's there |
|---|---|
| Site | Name, currency, timezone, plate validation (also the recognition country), public address |
| Parking rules | Receipts, exit payment, grace times, printer |
| Recognition | Who triggers the camera pictures, the two-reads-per-car limit, the photo on the driver's receipt page |
| Camera calibration | Each camera's zone, lines and minimum confidence |
| Mobile money | ClickPesa keys and switching on real money |
| Alerts | Who is told about manual openings and failed gate commands |

Values saved on screen are kept in the site database and override `zirp.env`.

The rest (database connection, ports, low-level tuning) live in
`C:\ProgramData\SmartParkEdge\config\zirp.env`, where `zirp.env` also gives
the starting value for the on-screen settings. Each setting starts with
`SMARTPARK_`. Editing the file needs an administrator. After a change, restart
the services:

```powershell
& "C:\Program Files\Zirp\bin\zirpctl.ps1" services restart
```

There's also a small helper that lists and checks settings, and hides secret
values:

```powershell
cd "C:\Program Files\Zirp\current"
.\python64\python.exe -m app.cli env list --changed
.\python64\python.exe -m app.cli env check
```

Most day-to-day settings (tariffs, parking rules, calibration, mobile money,
alerts) are in the desktop app under **Settings**, not in the file.

## What happens when things fail

| What fails | What Zirp does | What you do |
|---|---|---|
| A service crashes | Windows restarts it | Check its log if it keeps happening |
| Power cut during a barrier command | The command shows as *interrupted*; it's never re-sent blindly | Check the lane, retry from the desktop if needed |
| Power cut between a manual opening and its alert | The alert is still sent once the server is back | Nothing |
| A camera drops off the network | Reconnects in the background; the camera shows as disconnected | Check cable and power if it doesn't come back |
| Internet is down | Cash, kiosk, gates and exits keep working; mobile money and alerts wait | Nothing; they catch up |
| An update fails its health check | The previous version is switched back automatically | Read `logs\install\last-error.txt` |
| A database restore file is broken | Nothing is changed (one transaction) | Use another backup |

## Rebooting

After a reboot the services start on their own, before anyone signs in. Only
the camera SDK host waits for a sign-in, if you didn't install it as a service
(see [install.md](install.md#pick-a-role)). `tools\Test-RebootRecovery.ps1`
checks a planned reboot end to end.
