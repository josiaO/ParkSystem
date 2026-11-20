# Zirp — Windows productization audit, deployment architecture and release procedure

Status 2026-11-20: a per-machine installer is implemented and builds (`dist\installer\Zirp-Setup-1.0.0-rc1.exe`, 218 MB, unsigned). **It has not been installed on a clean machine yet. Zirp is not deployment-ready (Part C rule 8) until the checklist in §7 passes on clean VMs.**

§1 is the audit of the stack as it was found. §2 onwards describes the new installer.

## 1. Audit of the actual stack

| Item | Finding (source) |
|---|---|
| Desktop application | PySide6 / Qt 6.11 (`app/desktop`, started with `python -m app.desktop.launch`). Not Electron/Tauri — there is no desktop bundler to reuse. |
| Web UI | Static operator pages served by FastAPI (`app/web`), plus the **Next.js 16 portal** (`portal/`, public pay page and back office) which needs **Node ≥ 20.9** and an `npm run build` on site (`Register-PortalServices.ps1` throws if `node_modules`/`.next` are missing). Node is *not* in the kit. |
| Frontend build | `next build` (portal only). The Qt desktop and `app/web` need no build. |
| Backend runtime | CPython 3.11.9 **embedded** distribution, 64-bit (`python64/`) for Site Service, media, recognition and desktop; **32-bit** (`python32/`) for the QY/HVX SDK host. FastAPI + uvicorn, SQLAlchemy 2, Alembic. |
| Python / native deps | Pinned `requirements.txt`; wheels pre-downloaded to `packaging/cache/wheels-win64|win32` and installed offline by the installer. Native: onnxruntime, opencv-headless, numpy, PySide6, psycopg[binary], argon2. MSVC runtime DLLs for python64 and VC++ 2005 SP1 **x86** redistributable for the QY DLLs (hash-checked in `make_windows_kit.sh`). |
| Camera SDK | QY/OcxConfig NetSDK family: `NetSDK.dll CommModule.dll PlaySdk.dll RtspRecvSdk.dll DecodeSdk.dll Log.dll ZlibHelper.dll` (+ optional DevSearchHelper*), `OcxConfig.ocx`, `OcxConfigClient.exe`. Not in the repository; supplied via `SMARTPARK_HVX_VENDOR_DIR`. A SHA-256 manifest `QY-SDK-MANIFEST.txt` is generated. **Redistribution licence from the camera vendor is not documented anywhere in the repo.** |
| AI models | FastALPR ONNX detector (`yolo-v9-t-384-license-plates-end2end.onnx`, open-image-models) and OCR model (fast-plate-ocr), downloaded at kit build into `models/fastalpr`; offline at site. ONNX Runtime CPU. Model licences must be recorded with the kit. |
| Media | FFmpeg 7.1 (imageio-ffmpeg build, **GPL-3** → source-offer obligation when distributed), MediaMTX v1.11.3 (MIT) as optional sidecar owned by the Media Service. |
| Background workers | Windows services via **NSSM** (public domain), `LocalSystem`, auto-start, restart on exit: `SmartParkSiteService` (`app.site_service`, depends on local `postgresql*` when present) → `SmartParkMediaService` (`app.media_service`) → `SmartParkRecognitionWorker` (`app.recognition_worker`); `SmartParkHvxHost` (32-bit) as a service only with `-HvxHostAsService`, otherwise an at-logon scheduled task. Fallback: scheduled tasks when not elevated / no NSSM. In-process lane sweeper, payment and alert outboxes run inside the Site Service. |
| Database | PostgreSQL is the production authority (memory: LAN-first, PostgreSQL as truth). The kit does **not** install PostgreSQL; the Site Service only adds a service dependency on an existing `postgresql*` service. SQLite (`%ProgramData%\SmartParkEdge\smartpark.db`) is the development/default fallback. Backups use `pg_dump` from the PostgreSQL install. |
| Redis | **Not used.** No Redis client in `app/` or the requirements. Nothing to package. |
| Configuration | `%ProgramData%\SmartParkEdge\deployment.json` (role, server URL, installation id), `.env`/settings (`app/config.py`, `SMARTPARK_*`), DB config `app/database_config.py`, `site_settings` table for site policy. |
| Secrets | `SecretStore` (`app/infrastructure/secrets`): **DPAPI machine scope** on Windows (`data_dir/secrets/*.bin`), refs in the DB. Payment provider keys and DB password follow the same store. Nothing secret is in the kit today. |
| Persistent data | `%ProgramData%\SmartParkEdge\` — database (SQLite), `logs\`, `logs\services\`, media/captures, secrets, `kiosk_device.json`, locks. Install tree is replaced on upgrade; ProgramData is kept. Uninstall keeps ProgramData; `Wipe-SmartPark.bat` deletes it. |
| Install location | Default `%LOCALAPPDATA%\Programs\SmartPark Edge` (per-user) unless `-AllUsers` (`Program Files`). |
| Roles | `SITE_SERVER`, `EDGE_NODE`, `OPERATOR_CLIENT` (`app/deployment.py`, installer `-Role`). **No KIOSK role**: a kiosk is an OPERATOR_CLIENT desktop enrolled as a kiosk device (`kiosk_device.json`, "Kiosk Operator" role). |
| Versioning / signing | `pyproject` version `0.1.0` is not used for releases; `BUILD-INFO.txt` records build time, git base and script hashes. **No Authenticode signing**, no versioned install directories, **no rollback**. |
| Diagnostics | Startup check, server diagnostics, field acceptance test, logs shortcut, `RUNTIME` heartbeat lines, health endpoints. Good base. |

### Defects found that matter for productization

1. **Services run from a user profile.** On this PC every SmartPark service points at `C:\Users\PC\AppData\Local\Programs\SmartPark Edge\…` while the signed-in user is a different account. `tools/windows/zirp-desktop.ps1` resolves `%LOCALAPPDATA%` of the *current* user and fails ("Installed Python not found"). A LocalSystem service must not depend on a user profile: production installs must be per-machine (`Program Files`).
2. Portal requires Node and an on-site build — fails the "no developer tools" requirement.
3. Upgrade overwrites the install tree in place; a failed upgrade cannot be rolled back.
4. FFmpeg GPL and QY SDK redistribution terms are not tracked in a release licence manifest.
5. Pre-existing: migration `0020` fails on a database whose `cameras` table predates `stream_profiles` (seen in `test_sqlite_upgrade_from_0005_adds_exit_lane_columns`).

## 2. Packaging decision (implemented)

| Choice | Why |
|---|---|
| **Embedded CPython 3.11** (64-bit + 32-bit), all packages installed **at build time** | The 32-bit camera SDK needs its own interpreter; onnxruntime, Qt and ctypes-loaded vendor DLLs are fragile under PyInstaller. Packages are no longer installed on the customer's PC: the build installs them and smoke-tests the result. |
| **Inno Setup 6** installer (`packaging/installer/Zirp.iss`) | Standard professional Windows installer: per-machine, wizard pages, Start Menu, uninstaller, Authenticode signing, silent install for IT. WiX/MSI only if a customer requires GPO deployment. |
| **Versioned side-by-side install + `current` junction** | Upgrade = install beside the old version, switch, health-check; rollback = switch back. |
| **NSSM** services (kept) | Already proven on site for these processes; restart policy and log capture unchanged. |
| **Portal: Next.js standalone build + bundled `node.exe`** | No Node, npm or build on site. |
| PyInstaller | Rejected (see above). |

The old USB kit (`packaging/make_windows_kit.sh`, `packaging/windows/*`) was removed from the repository on 2026-11-20; this installer is the only one. It still detects an old kit on a site PC and takes over from it (§4).

## 3. What gets installed where

```
C:\Program Files\Zirp\
    versions\1.0.0-rc1\   app\ tools\ models\ portal\ python64\ python32\ vendor\ VERSION BUILD-INFO.json
    versions\<previous>\  kept for rollback (current + previous are kept, older ones pruned)
    current  ->  versions\1.0.0-rc1          junction; every service and shortcut uses \current
    bin\  zirpctl.ps1  Zirp-Kiosk.ps1  zirp.ico
C:\ProgramData\SmartParkEdge\                 never touched by upgrades or (by default) uninstall
    config\zirp.env  config\portal.env        settings (zirp.env preferred; old <install>\.env still read)
    install\role.json                          role chosen in the installer (read by the desktop)
    backups\pre-upgrade\*.sql (+ .json)        dump taken before every upgrade (Administrators/SYSTEM only)
    logs\install\zirpctl-*.log, history.jsonl  every activation / rollback
    deployment.json, secrets\ (DPAPI), media, logs ...
HKLM\SOFTWARE\Zirp                             InstallDir, CurrentVersion, PreviousVersion, Role, KioskUser, HvxAsService
```

## 4. Roles (installer page "Role of this computer")

| Choice | Deployment role / station | Services | Extras |
|---|---|---|---|
| Site Server with cameras (single-computer site) — `COMBINED` | `SITE_SERVER` | Site Service, Media (MediaMTX), Recognition Worker, camera SDK host, Portal | LAN-only firewall rules |
| Site Server only — `SERVER` | `SITE_SERVER` | Site Service, Portal | |
| Edge Node — `EDGE` | `EDGE_NODE` | Site Service, Media, Recognition Worker, camera SDK host | |
| Operator Workstation — `OPERATOR` | `OPERATOR_CLIENT` | none (old ones removed) | desktop shortcut |
| **Payment Kiosk** — `KIOSK` | `OPERATOR_CLIENT` + station `KIOSK` | none | task **Zirp Kiosk**: at sign-in of the kiosk account, starts the desktop **full screen** and restarts it if closed; first start opens kiosk-device enrolment |

Camera SDK host: a page asks whether to run it as a Windows service (works with nobody signed in) or at user sign-in (default, as before, until verified on the camera model).

Taking over an old per-user kit on another site PC (this development PC was cleaned by hand on 2026-11-20 instead: old services, firewall rules, shortcuts, environment variables and the install folder removed; settings already copied to `config\zirp.env` / `config\portal.env`; PostgreSQL dump in `backups\pre-cleanup\`): activation removes old `SmartPark*` service and task registrations that point outside `Program Files\Zirp`, copies `<old>\.env` → `config\zirp.env` and the portal settings once, and **leaves the old files** to delete after the new install is confirmed. The database in ProgramData is shared, so nothing is migrated.

Silent install for IT: `Zirp-Setup-1.0.0.exe /VERYSILENT /ROLE=OPERATOR` (`/RECONFIGURE=1` shows the role pages again on an upgrade).

## 5. Upgrade, rollback, uninstall

`zirpctl activate` (run by the installer after copying files):
1. VC++ x64 and VC++ 2005 x86 runtimes (silent, idempotent).
2. Take over an old kit if present.
3. Stop services; **pre-upgrade database dump** with the outgoing version (`python -m app.release_tool backup`, records the schema revision). If the dump fails, nothing is changed.
4. Switch `current` to the new version; register services for the role; start; wait for `/health/live` (180 s; first start runs migrations).
5. **Not healthy → automatic switch back** to the previous version and restart; the installer reports the failure.
6. Record state; keep current + previous version and the last 5 dumps.

Rollback (Administrator PowerShell):
```
& "C:\Program Files\Zirp\bin\zirpctl.ps1" rollback                      # code only, to the previous version
& "C:\Program Files\Zirp\bin\zirpctl.ps1" rollback -RestoreDatabase     # also restore the pre-upgrade dump (type RESTORE)
& "C:\Program Files\Zirp\bin\zirpctl.ps1" rollback -To 1.0.0            # any installed version
```
Code-only rollback is safe for additive migrations (all current ones). `-RestoreDatabase` removes visits and payments recorded since the upgrade; the database it replaces is kept (SQLite: renamed file; PostgreSQL: another dump).

Other commands: `status`, `services start|stop|restart|install|remove`, `backup`, `uninstall`, `purge-data -Force` (factory reset: on a Site Server it also empties the PostgreSQL database after you type its name; on an Edge Node whose photos the site database references it refuses, so records never point at missing photos).

Uninstall (Apps & features): removes services, tasks, firewall rules and `Program Files\Zirp`. On an Operator or Kiosk PC it then asks whether to delete `C:\ProgramData\SmartParkEdge` — **default No**. On a Server or Edge Node it never deletes data (use `purge-data` first for a factory reset). A silent uninstall never deletes data.

LAN distribution: a Site Server keeps a copy of its installer in `Program Files\Zirp\installers\`; other PCs download it from `http://<server>:8760/downloads/zirp-setup.exe` (link on the web sign-in page).

## 6. Build, sign and release

Build machine needs Node 20.9+, Inno Setup 6, the cached embedded Python zips (`packaging\cache`), and the third-party payload (camera SDK, ffmpeg, mediamtx, nssm, VC++ redistributables, models, wheels) in `packaging\thirdparty` (git-ignored, never commit). If no Python 3.11 with pip is found, the build bootstraps a private one in `build\toolchain` from the cached embedded Python and pip wheel.

```
powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.0.0
powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.0.0 -CertThumbprint <SHA1>
```

The build stages the release → checks the camera SDK against its SHA-256 manifest → installs wheels into the bundled runtime → smoke-tests it (imports the whole Site Service and desktop, ONNX CPU provider, 32-bit check) → builds the portal standalone → **secret scan** (fails on any settings file, key, certificate, database or credential) → signs (if a certificate is given) → compiles → writes `.sha256` and `BUILD-INFO.json`.

Signing: Authenticode SHA-256 with an RFC-3161 timestamp on the installer, the uninstaller and the shipped PowerShell tools. Certificate from the Windows certificate store (`-CertThumbprint`, works with hardware tokens/EV certificates) or `ZIRP_SIGN_PFX` + `ZIRP_SIGN_PFX_PASSWORD`. Needs `signtool.exe` (Windows SDK). Never commit a certificate. Without one the build is unsigned and `BUILD-INFO.json` says `"signed": false`.

Release: tag → signed build → §7 on clean VMs → publish the `.exe`, `.sha256` and `BUILD-INFO.json`; keep the previous installer.

Verified on 2026-11-20 on this PC: stage build and smoke test pass; secret scan clean; `Zirp-Setup-1.0.0-rc1.exe` compiles (218 MB, version resource 1.0.0.0, unsigned); `zirpctl status` and error paths on a temporary root; release-tool backup → restore round trip; kiosk station config. **Not run here: an actual install, upgrade or rollback**, because it would remove this site's live services.

## 7. Clean-machine acceptance checklist

On fresh Windows 10 22H2 and Windows 11 x64 VMs (no Python, Node, Git or VC++ runtimes), for each role:

- [ ] Installer shows the publisher (signed) or "Unknown publisher" (unsigned build); asks for elevation once.
- [ ] Role page; Kiosk asks for the account; camera-host page only for Combined/Edge.
- [ ] Files in `C:\Program Files\Zirp\versions\<v>`, `current` junction, `HKLM\SOFTWARE\Zirp` filled.
- [ ] Combined/Server/Edge: services exist, `LocalSystem`, automatic, paths under `Program Files\Zirp\current`, start after reboot with nobody signed in.
- [ ] Operator/Kiosk: no Zirp services.
- [ ] First start: setup wizard locked to the installed role; database settings and payment keys stored via DPAPI, absent from files and logs.
- [ ] `/health/live` answers; portal opens from another LAN PC (no Node on either).
- [ ] Start Menu: Zirp, Web, Portal, startup check, status, logs; desktop icon optional.
- [ ] Kiosk: sign in as the kiosk account → enrolment prompt → full screen; close it → it comes back; reboot → still enrolled.
- [ ] **Hardware**: QY camera login and live video, plate read, barrier opens, receipt printer, QR scanner, passage loop if fitted.
- [ ] Upgrade rc1 → rc2: pre-upgrade dump in `backups\pre-upgrade`; settings, secrets and enrolments kept; services healthy.
- [ ] Broken upgrade (e.g. stop PostgreSQL during activation): installer reports the failure, previous version running again.
- [ ] `zirpctl rollback` and `rollback -RestoreDatabase` work; parking works afterwards.
- [ ] Taking over an old USB-kit install: old services removed, `.env` carried over, parking works.
- [ ] Uninstall: services, tasks, firewall rules and files gone; ProgramData kept by default; "delete data" removes it.
- [ ] Linked vehicles field steps (docs/LINKED_VEHICLE_AUTHORIZATION.md §5).

## 8. Gaps from the audit — status

| Gap | Status |
|---|---|
| No Kiosk role in the installer | **Done**: `KIOSK` role, `station` in `deployment.json`, full-screen kiosk desktop, auto-start and restart task, enrolment on first start. |
| No code signing | **Done in the build** (installer, uninstaller, PowerShell tools). Needs a code-signing certificate to produce signed releases. |
| No rollback | **Done**: versioned installs, pre-upgrade dump, automatic switch-back on a failed health check, `zirpctl rollback [-RestoreDatabase]`. |
| Redis | Nothing to package: Zirp does not use Redis. Queues and outboxes live in PostgreSQL by design (LAN-first). |
| Services run from another user's profile | **Fixed** for new installs (per-machine `Program Files`, takes over the old kit). `Restart-Zirp-Desktop.cmd` on this PC now finds the runtime through the running service. |
| Portal needs Node and an on-site build | **Done**: standalone build plus bundled node.exe. |
| Settings file inside the program folder | **Done**: `ProgramData\SmartParkEdge\config\zirp.env` preferred. |

## 9. Unresolved risks

1. Nothing has been installed on a clean machine yet (§7).
2. No code-signing certificate yet → SmartScreen warning on download.
3. QY camera SDK redistribution licence unknown; FFmpeg is GPL-3 (source offer needed).
4. VC++ 2005 SP1 x86 (end of support) is required by the camera SDK.
5. PostgreSQL is still installed separately; `-RestoreDatabase` on PostgreSQL needs `psql` on the PATH or `SMARTPARK_PSQL`.
6. A FastALPR model pack applied from the desktop is written into the version folder and does not carry over to the next version; re-apply it after an upgrade.
7. A relative SQLite path in settings resolves against the version folder; use the default (ProgramData) or an absolute path.
8. DPAPI machine-scope secrets are readable by local administrators/LocalSystem (appliance model).
9. Services still run as LocalSystem; least-privilege service accounts are a later hardening step.
