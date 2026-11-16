# Zirp — Documentation Cleanup Assessment

Investigation date: 2026-11-14, HEAD `8a29f85`. Classified only after tracing the code (see `ZIRP_ENGINEERING_HANDOVER.md`). **No document was modified or deleted.**

Categories: **Keep** (accurate, operationally useful) · **Update** (useful, inconsistent with code) · **Archive** (historical evidence / superseded design) · **Delete** (irrelevant, misleading, duplicate) · **Verify** (accuracy needs hardware/field evidence).

## A. Documents present in the working tree

| Document | Class | Reason |
|---|---|---|
| `docs/ZIRP MASTER_PROJECT_ONBOARDING.md` (untracked) | Keep | Current owner brief for this onboarding. |
| `docs-site/` (`index.html`, `README.md`, `app.js`, `styles.css`) | Update | The most accurate operator/technician document. Its startup section matches the code (scheduled tasks at user logon) and states why a Windows service is "advanced". Needs updates once D2 (receipt-taken sensor), D3 (`/auth/setup`), D5 (autostart) are resolved, and should state that a production casual entry currently cannot auto-open. |
| `packaging/windows/README-USB.txt` | Keep | Matches `Install-SmartPark.ps1` (single installer, three roles). |
| `tools/hvx_sdk_host/README.md` | Verify | Describes the vendor DLL set and the 32-bit host, consistent with the code. The DLLs are present locally in `Current_ParkSystem_configs/Camera_config/OcxConfig/` (PE32, NetSDK 3.2.3.6) and match the built kit. Still needs checking against the firmware and DLLs on the Rock City Mall cameras. |
| `tools/hvx_sdk_host/vendor/README.md` | Keep | Placeholder explaining that vendor binaries are not committed. |
| `vendor/mediamtx/README.md` | Keep | Accurate (binary not committed; kit bundles it). |
| `app/web/MEDIAMTX-NOTICE.md` | Keep | Licence notice. |
| `packaging/licenses/FFmpeg-GPL-3.txt` | Keep | Licence obligation for the bundled FFmpeg. |
| `app/api/runtime_parts/README.md` | Keep (until refactor) | Accurately maps the 14 exec-loaded runtime parts. Becomes obsolete when D10 is done. |
| `SMARTPARK-ARCHITECTURE-AND-AUDITS.html` (root, 62 KB) | Archive | Point-in-time architecture + audit report with a "recommended resilient architecture" proposal. Historical; not a description of the current code. Move under `research/` or an `archive/` folder. |
| `architecture.svg` (root) | Archive | Conceptual layer picture ("Edge media engine", "Event coordinator") that does not map to actual modules/processes. |
| `research/parkwatch/*.md` (+ `evidence/`, `project/`, `scripts/`) | Archive (keep in repo) | Reverse-engineering evidence of the previous ParkWatch install. Valuable provenance for QY/NetSDK behaviour. `SMARTPARK_GAP_ANALYSIS.md` and `SMARTPARK_IMPROVEMENT_PLAN.md` are dated 2026-10-14; several P0 items (capture tokens, replay) were since addressed in code (`capture_token` in `hvx_host.py`), so treat them as history, not a backlog. |
| `research/ocxconfig/*` | Archive (keep in repo) | Ghidra evidence for the OcxConfig `NetSDK.dll` build actually used by the host. Keep as reference. |
| `research/optimization-2026-10-15/*` | Archive | Historical repair notes + test logs from an earlier iteration. |
| `research/desktop-ui/*` | Archive | UI preview images. |
| `.cursor/mcp.json` | Delete | Empty editor config; not documentation. |
| `:memory:.ses` (root, tracked) | Delete | Stray runtime artefact, not documentation. |
| Root images `TZ_plates.webp`, `TZ_paltes.jpeg`, `images*.jpeg` | Verify | Plate samples; if they are test fixtures move them under `tests/fixtures`, otherwise remove from the root. Check image rights first. |

## B. Documents removed by HEAD commit `8a29f85` ("removed docs")

These no longer exist in the working tree but remain in git history (`git show 5ebbcec:<path>`). Recommendation is for what to do *if* any are restored or referenced.

| Document | Class | Reason |
|---|---|---|
| `README.md` | Update (restore a short one) | The repo currently has no README at all. Write a new, short README from the handover (entry points, roles, how to run tests); do not restore the old one verbatim. |
| `docs/DEPLOYMENT.md` | Update | Technician runbook; content overlaps docs-site. Fold into docs-site rather than keep two copies. |
| `docs/POSTGRESQL-PREREQUISITE.md` | Update | Operationally useful for multi-PC; restore after checking against `app/database_config.py` and `Repair-SmartParkNetwork.ps1`. |
| `docs/LANE-DEPLOYMENT.md` | Verify | Describes node/gate ownership; matches the node-scope code in outline but multi-PC operation is untested. |
| `docs/DATABASE_CONFIGURATION.md` | Update | Useful; check against `deployment.json` + secret store flow. |
| `docs/SYSTEM-GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/MEDIA-ARCHITECTURE.md`, `docs/FASTALPR-PIPELINE.md`, `docs/MEDIAMTX-INTEGRATION.md`, `docs/NATIVE-ALPR.md`, `docs/STREAM-PROFILES.md` | Archive | Generated architecture descriptions from earlier iterations. Superseded by the handover's code-derived description; keep only in history. |
| `docs/CAMERA-*.md`, `docs/ADDING-A-CAMERA-VENDOR.md`, `docs/ADDING-A-RECOGNITION-PROVIDER.md`, `docs/GATE-ADAPTERS.md` | Archive | Short extension guides; the "adding a recognition provider" guide implies a pluggable multi-engine system, but only FastALPR exists. |
| `docs/CAMERA-TROUBLESHOOTING.md`, `docs/CAMERA-DELIVERY-DIAGNOSTICS.md`, `docs/engineering/windows-field-diagnostics.md` | Verify | Potentially useful field procedures; need checking against current diagnostics scripts before restoring into docs-site. |
| `docs/engineering/streaming-*.md` (audit, baseline, target architecture, acceptance checklist) | Archive | Historical streaming investigation and a proposed target architecture. |
| `docs/MIGRATION-AND-ROLLBACK.md`, `docs/CAMERA-ENGINE-MIGRATION.md` | Archive | Migration proposals; rollback is not actually implemented beyond re-installing a previous kit. |
| `ZIRP PLATFORM ARCHITECTURE.md` (1181 lines) | Archive | An instruction prompt to an AI agent proposing a future platform split, not a description of the system. Not binding. |
| `CODEX ENGINEERING TASK.md`, `CODEX_ENGINEERING_TASK 01.md` | Archive | Old AI-agent task prompts. Not binding. |
| `READ ONLYTECHNICALAUDIT-results.txt` | Delete | An audit of a **different repository** (`/home/josiamosses/aperture`, "SeasonPass"). Irrelevant to Zirp. |

## C. Recommended documentation set (target)

1. `README.md` — what Zirp is, processes, how to run/test locally (new).
2. `docs-site/` — single operator/technician manual (deployment, PostgreSQL, field diagnostics folded in).
3. `docs/ZIRP_ENGINEERING_HANDOVER.md` — engineering reference, kept current as defects close.
4. `research/` — vendor evidence, untouched.
5. Everything else archived in git history only.
