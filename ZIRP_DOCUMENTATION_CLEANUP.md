# Zirp: Documentation Cleanup Assessment

Investigation date 2026-11-16, HEAD `04105ff`. Documents were classified only after tracing the code (see `ZIRP_ENGINEERING_HANDOVER.md`). **No document was modified, moved or deleted.**

Categories:
- **Keep**: accurate and operationally useful.
- **Update**: useful but inconsistent with the code.
- **Archive**: historical evidence or superseded design.
- **Delete**: irrelevant, misleading, duplicate or obsolete.
- **Verify**: accuracy cannot be settled without hardware or field evidence.

## Context

The HEAD commit deleted README.md, `SMARTPARK-ARCHITECTURE-AND-AUDITS.html` and nine runbooks under `docs/`: CAMERA-TROUBLESHOOTING, DATABASE_CONFIGURATION, DEPLOYMENT, LANE-DEPLOYMENT, OFFLINE-OPTIONS, POSTGRESQL-PREREQUISITE, RECOGNITION-MEASUREMENTS, SOAK-TEST and WINDOWS-SERVICES. The working tree additionally deletes `docs/WINDOWS-TEST-PROTOCOL.md` (uncommitted). Those files remain retrievable from git history (`git show 04105ff^:docs/<name>`).

Several **live code paths and scripts still point at deleted docs**:
- `packaging/windows/Install-SmartParkWinService.ps1` (`docs\WINDOWS-SERVICES.md`)
- `packaging/windows/Run-LatencyTest.ps1`
- `packaging/make_windows_kit.sh` (now skips missing docs, per commit `f76a575`)
- `app/infrastructure/recognition/engines/fastalpr.py`
- `tests/test_windows_packaging.py`, `tests/test_migration_architecture.py`

Operators following installer messages are sent to files that no longer exist.

## A. Documents present in the working tree

| Document | Class | Reason |
|---|---|---|
| `docs/ZIRP MASTER_PROJECT_ONBOARDING.md` | Keep | Current owner brief. Its "local" path (`/home/...`) is from a Linux machine; the active checkout is now `C:\SmartParkEdge`. |
| `ZIRP_ENGINEERING_HANDOVER.md` (root, this investigation) | Keep | Current handover against `04105ff`. |
| `ZIRP_DOCUMENTATION_CLEANUP.md` (root, this file) | Keep | |
| `docs/ZIRP_ENGINEERING_HANDOVER.md` (2026-11-14, HEAD `8a29f85`) | Archive | Superseded. About half of its defects are fixed (models tracked, `/auth/setup`, outbox dead letter, stale replay, adapter validation, operator mobile money). It still cites file names that no longer exist (`app/models/40_parking.py`) and an `AtLogOn`-only service model. Useful as a record of what was fixed and why. |
| `docs/ZIRP_DOCUMENTATION_CLEANUP.md` (2026-11-14) | Archive | Superseded by this file; describes documents that have since been deleted. |
| `docs/WINDOWS-TEST-PROTOCOL.md` (deleted in working tree, still in HEAD) | Verify, then restore or delete | It is the operator procedure for the latency kits (`Latency-A1/A2/A3.bat`) still shipped in `packaging/windows/`. If those kits are to be run (roadmap step 8), the protocol is needed; the deletion looks accidental relative to the kits. Decide before committing the deletion. |
| `CLAUDE_CODE_TASK.md` (root) | Archive | AI-agent work order (phases, "do not touch" rules). Not binding per the onboarding brief; several of its tasks are already implemented. Historical instruction, not documentation of the system. |
| `CLAUDE_CODE_STALE_AND_BOOM.md` (root) | Archive | AI-agent brief for the stale-display and boom-latency investigation. Its "what the code looks like today" section is stale (says `hvx_host.py` is about 390 lines; it is 589 plus 2.8k lines in `hvx_sdk_parts/`). Keep only as context for the latency kits. |
| `docs-site/` (`index.html`, `README.md`, `app.js`, `styles.css`) | Update | Production documentation website for technicians. Must be checked against: NSSM services for three processes but the HVX host still as a logon task; the production operator override for receipts (D1); passage sensing requirements (D2); and links to runbooks deleted in HEAD. |
| `app/api/runtime_parts/README.md` | Keep (until refactor) | Accurately describes the exec-loaded parts. Obsolete once D11 is done. |
| `app/web/MEDIAMTX-NOTICE.md` | Keep | Licence notice. |
| `packaging/licenses/FFmpeg-GPL-3.txt`, `NSSM-public-domain.txt` | Keep | Licence obligations for bundled binaries. |
| `packaging/windows/README-USB.txt` | Verify | Kit README; check that it matches current installer behaviour (NSSM default, HVX host logon task) on a real install. |
| `tools/hvx_sdk_host/README.md` | Verify | Vendor DLL list and 32-bit host description match the code; must be checked against the DLL and firmware versions at Rock City Mall. |
| `tools/hvx_sdk_host/vendor/README.md` | Keep | Explains why vendor binaries are not committed. |
| `vendor/mediamtx/README.md` | Keep | Binary not committed; kit bundles it. |
| `tests/fixtures/latency/fake-sdk-dryrun/README.md` | Keep | Describes fixture provenance (fake SDK, not hardware). |
| `architecture.svg` (root) | Archive | Conceptual layers that do not map to actual processes or modules (see handover section 5 for the real diagram). |
| `research/parkwatch/*` (markdown + Ghidra evidence) | Archive (keep in repo) | Reverse-engineering evidence of the previous ParkWatch install; useful provenance for QY/NetSDK behaviour, not a description of Zirp. |
| `research/ocxconfig/*` | Archive (keep in repo) | Ghidra evidence for the OcxConfig `NetSDK.dll` build the host binds to (`tools/hvx_sdk_host/hvx_bindings.json`). |
| `research/optimization-2026-10-15/*` | Archive | Historical repair notes and test logs. |
| `research/desktop-ui/*` | Archive | UI preview images. |
| Root images `TZ_plates.webp`, `TZ_paltes.jpeg`, `images*.jpeg` | Verify | Plate sample images in the repository root. If used as recognition fixtures, move them under `tests/fixtures/`; otherwise remove. Check image rights first. |
| `app/api_main.py::LEGACY_SOURCE_MARKERS` (inline text, not a doc) | Delete (with test change) | Inert string kept only so source-text tests pass. Misleading: it looks like code. |

## B. Documents deleted by HEAD `04105ff` (recoverable from git)

| Document | Recommendation | Reason |
|---|---|---|
| `README.md` | Restore a short one | A repository with no README gives no entry point. A 30-line README pointing to the handover, `docs-site/` and the start commands is enough. |
| `docs/WINDOWS-SERVICES.md` | Restore (Update) | Referenced by `Install-SmartParkWinService.ps1` for the HVX host auto-logon procedure (D5). |
| `docs/DEPLOYMENT.md`, `LANE-DEPLOYMENT.md`, `DATABASE_CONFIGURATION.md`, `POSTGRESQL-PREREQUISITE.md` | Verify, then fold into `docs-site/` | Multi-PC setup is real in code (node roles, PostgreSQL, shared media dir). Technicians need one current procedure, not four. |
| `docs/OFFLINE-OPTIONS.md` | Archive | Design options note (read replica vs outbox), not current behaviour. |
| `docs/RECOGNITION-MEASUREMENTS.md`, `SOAK-TEST.md`, `CAMERA-TROUBLESHOOTING.md` | Verify | Field procedures tied to `tools/` scripts that still exist; restore whichever the field team still uses. |
| `SMARTPARK-ARCHITECTURE-AND-AUDITS.html` | Leave deleted (Archive in history) | Point-in-time audit and proposed architecture; superseded. |

## C. Suggested follow-up (not done)

1. Decide on `docs/WINDOWS-TEST-PROTOCOL.md` before committing its deletion.
2. Restore a minimal `README.md` and `docs/WINDOWS-SERVICES.md`, or change the installer messages that reference them.
3. Move `CLAUDE_CODE_*.md`, the 2026-11-14 handover/cleanup files and `architecture.svg` into an `archive/` folder.
4. Update `docs-site/` after D1/D2/D5 are resolved.
