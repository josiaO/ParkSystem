# System recheck and Windows kit rebuild

Date: 19 October 2026.

Historical report: the shared `dist/SmartParkEdge-USB.zip` was rebuilt again on
21 October 2026 for the camera/recognition/UI fixes. See
`WINDOWS_CAMERA_UI_FIXES.md` and the current external manifest/checksum for that
newer artifact. The size, checksum, file counts, and test results below describe
the 19 October build, not the replacement archive.

## Outcome

The Windows USB kit was rebuilt from the current working tree, including the production-stabilization work and the native desktop UI rebuild. No engine, UI, or installer source code was changed during this recheck. The previous generated kit contained a forbidden PySide6 Addons wheel; the existing build script correctly excludes it in the rebuilt payload.

The artifact passes the available automated checks. This is **not** a claim that the installation or physical parking workflow has been validated on Windows hardware.

## Deliverables

- `dist/SmartParkEdge-USB.zip` — rebuilt USB archive, 256,092,980 bytes (approximately 244.2 MiB).
- `dist/SmartParkEdge-Install/` — unpacked installation folder; copy the entire folder to USB.
- `dist/SmartParkEdge-USB.zip.sha256` — archive checksum.
- `dist/SmartParkEdge-USB.manifest.json` — archive identity, source revision context, exact wheel versions, executable architectures, and SHA-256 hashes for all 357 packaged files.

Archive SHA-256:

```text
3be2efd41bbbcbbc944e61c70b8c80ac95847bcd08e218365ff64eb576a0397a
```

The kit targets Windows x64 with embedded CPython 3.11.9 and a separate x86 Python/HVX SDK host. The build reused the existing download cache with offline wheel resolution; no dependency upgrade or network download was needed.

## System checks

- Initial unrestricted Python suite: **656 passed, 5 failed**, plus 3 passing subtests. Four failures concerned previously missing documentation; the fifth identified the forbidden wheel in the old generated kit.
- Post-rebuild suite: **657 passed, 4 deselected**, plus 3 passing subtests. All runtime, desktop, and payload checks passed. Only the four confirmed documentation checks below were excluded; no tests were edited or disabled in source.
- One non-blocking existing Starlette/httpx test-client deprecation warning remains. Dependencies were not changed to suppress it.
- Browser WHEP regression script passed under Node.
- Python compilation of `app`, `tools`, and `packaging` passed.
- All Windows PowerShell scripts parsed successfully using PowerShell's parser; the build shell script passed `bash -n`.
- `git diff --check` passed.

The post-rebuild suite was run with isolated temporary runtime data and offscreen Qt rendering:

```bash
SMARTPARK_DATA_DIR=/tmp/smartpark-system-postkit-20261019 \
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  --deselect=tests/test_migration_architecture.py::OperatorStatusTests::test_required_docs_exist \
  --deselect=tests/test_modules.py::DocsExistTests::test_module_docs_tree \
  --deselect=tests/test_ui_productization.py::ProductUiTests::test_ui_docs_exist \
  --deselect=tests/test_windows_packaging.py::WindowsPackagingTests::test_production_tree_is_this_rebuild
```

The excluded checks require legacy files such as `docs/MEDIA-ARCHITECTURE.md`, `docs/modules/OVERVIEW.md`, and `docs/ui/UI-ARCHITECTURE.md`. Those documentation gaps remain unresolved; they are not runtime failures and were not concealed by manufacturing placeholder files.

## Payload and archive checks

- The standard `packaging/verify_windows_kit.py` verifier passed.
- All **57 bundled wheels** passed ZIP CRC checks, Windows x64/CPython 3.11-compatible tag checks, and Python-version constraints.
- Every active bundled dependency was checked against its installed wheel version using Windows/Python 3.11 markers, including requested and propagated extras. Root requirements also match the bundled versions. No missing or conflicting active dependencies were found.
- All **180 application files** match the current source tree byte-for-byte, excluding Python caches. This includes the new desktop shell/presentation modules and stabilization migration.
- Packaged installer scripts that correspond to source files match those sources byte-for-byte.
- All **185 packaged Python source files** parse using Python 3.11 syntax rules, in addition to compilation/tests on this Linux development environment's Python 3.12.
- PE headers confirm x64 Python, FFmpeg, and MediaMTX executables, and x86 Python plus the six required HVX SDK DLLs.
- Both bundled ONNX models loaded and executed a zero-input CPU smoke inference successfully using the development environment's ONNX Runtime. This verifies model readability/execution here, not Windows compatibility, recognition accuracy, or field latency.
- The final ZIP passed CRC verification and matches the unpacked installation folder byte-for-byte for all **357 files**. The external SHA-256 checksum also verifies successfully.
- A filename scan found no site database, `.env`, first-run password file, or private-key file in the kit. This is a targeted packaging check, not a comprehensive secret-content audit.

To rerun the standard artifact checks:

```bash
.venv/bin/python packaging/verify_windows_kit.py dist/SmartParkEdge-Install/payload
(cd dist && sha256sum -c SmartParkEdge-USB.zip.sha256)
```

## Windows handoff

1. Preserve the existing site's database, `.env`, and credentials before installing an update.
2. Copy the complete `SmartParkEdge-Install` folder to the Windows PC, or extract the ZIP. Run `Install-SmartPark.bat` from that complete folder.
3. Follow `FIRST_TEST_WINDOWS.md` and the existing stabilization report for service configuration, per-PC gate ownership, camera diagnostics, and field acceptance.
4. Validate real Windows installation, background-task startup, native desktop scaling/keyboard/screen-reader behavior, actual live video, reconnects, stopped-vehicle recognition latency, duplicate prevention, printer acknowledgements, barrier behavior, and sustained multi-camera operation before production rollout.

No live cameras, printer, physical barrier, or real payment action was exercised during this recheck. A Windows host was not available for executing the installer or its bundled Windows Python/wheels.
