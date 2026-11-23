# Developing Zirp

## Getting the code running

You need Python 3.11 or 3.12. Linux works for nearly everything except the
camera SDK host, which is Windows-only and 32-bit.

```bash
git clone https://github.com/josiaO/ParkSystem.git
cd ParkSystem
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Run the Site Service with a local SQLite database:

```bash
python -m app.site_service          # http://127.0.0.1:8760
python -m app.desktop.launch        # the operator desktop
```

The portal is a normal Next.js app:

```bash
cd portal
npm install
npm run dev                         # http://localhost:3000
```

## Tests

```bash
pytest -q
```

That's around 1,400 tests and takes a few minutes. Some tests only run when
you give them a **throwaway** PostgreSQL database. They drop and recreate every
table, so never point them at a real site:

```bash
export ZIRP_TEST_POSTGRES_URL=postgresql+psycopg://user@127.0.0.1:55432/zirp_test
pytest tests/test_linked_vehicle_groups.py tests/test_production_audit_2026_11.py
```

A disposable cluster is quick to make with the PostgreSQL binaries:

```bash
initdb -D /tmp/pgtest -U audit -A trust
pg_ctl -D /tmp/pgtest -o "-p 55432 -c listen_addresses=127.0.0.1" start
createdb -h 127.0.0.1 -p 55432 -U audit zirp_test
```

### On a Windows build PC

The installer build leaves a complete runtime in
`build\installer\stage\python64`. It has every dependency except pytest, and
it ignores `PYTHONPATH`. Install pytest into a separate folder and run it with
a small script that puts that folder and the repository first on `sys.path`.
Two things to watch:

- `python -m app.something` with that runtime imports the **staged copy** in
  `build\installer\stage\app`, not your checkout. Go through a script that adds
  the repo to `sys.path`.
- Guard `pytest.main()` with `if __name__ == "__main__":`, or the
  multiprocessing tests will start the whole suite again in every child.
- Set `SMARTPARK_ENV_FILE` to an empty file, or the tests read the PC's real
  `zirp.env`.

## Conventions

- **Database changes are Alembic migrations** in
  `app/migrations/alembic/versions/`, numbered `00NN_short_name.py`. Keep them
  additive where you can: code rollback relies on that.
- **Never decide on stale data**, and **commit before you move hardware**. See
  [architecture.md](architecture.md).
- Tests that guard a production incident say so in their docstring.
- Secrets never go in the repository. The build fails if it finds a settings
  file, key or database in the payload.

## Building the installer

On a Windows PC with Inno Setup 6 and Node 20.9+:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\installer\build.ps1 -Version 1.0.0-rc5
```

Third-party files that can't live in git (camera SDK DLLs, FFmpeg, MediaMTX,
NSSM, VC++ runtimes, models and wheels) go in `packaging\thirdparty` and
`packaging\cache`. Redis for Windows is optional: put `redis-server.exe` and
its DLLs in `packaging\thirdparty\vendor\redis` and camera PCs get the
`SmartParkCache` service. Zirp talks to it with its own small client
(`app/services/shared_cache.py`), so no extra Python package is needed. The build:

1. stages the app, models and an embedded Python with every package installed,
2. checks the camera SDK against its hash manifest,
3. smoke-tests the staged runtime (imports, ONNX),
4. builds the portal as a standalone bundle with its own `node.exe`,
5. scans the payload for secrets,
6. signs (if you pass `-CertThumbprint`) and compiles
   `dist\installer\Zirp-Setup-<version>.exe`, plus a `.sha256` and
   `BUILD-INFO.json`.

Build from a clean commit: `BUILD-INFO.json` records the commit and whether
the tree was dirty.

### The installer ships compiled code

Like the parking systems that came before it, an installed Zirp contains the
compiled program, not its source. After staging, the build runs
`packaging/installer/compile_app.py` with the bundled Python:

- the numbered part files of the split modules (the API's `runtime_parts`,
  the desktop, the media gateway and so on) become `<part>.partc`, loaded by
  `app/core/parts.py`;
- every other module becomes a `.pyc` where its `.py` was;
- only `app/migrations/alembic` stays as source, because Alembic loads it by
  path. `tools/` (diagnostics) and the camera SDK host are not part of `app`.

The smoke test then imports every service, the desktop and the migration chain
from the compiled stage, so a build that would not run never becomes an
installer. `tests/test_compiled_release.py` does the same on every test run.
For a debugging build that keeps the source, add `-IncludeSource`.

## Releasing

1. Commit and push.
2. Build the installer from that commit.
3. Install it on a test PC for each role you changed.
4. Publish:

   ```powershell
   gh release create v1.0.0-rc5 --prerelease --title "Zirp 1.0.0-rc5" `
     dist\installer\Zirp-Setup-1.0.0-rc5.exe `
     dist\installer\Zirp-Setup-1.0.0-rc5.exe.sha256 `
     dist\installer\Zirp-Setup-1.0.0-rc5.BUILD-INFO.json
   ```

The installer is about 230 MB, so the upload takes a while on a slow line.
