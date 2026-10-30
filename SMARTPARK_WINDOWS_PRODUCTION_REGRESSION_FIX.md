# SmartPark Windows Stabilization Task for Cursor

## Mission

The `check` branch introduced production/deployment changes after the
system had already been working on Windows. Since those changes, fresh
installation and startup have become unreliable.

Observed failures are **not always at the same stage**:

-   sometimes the Windows installation fails;
-   sometimes installation completes but the recognition pipeline fails;
-   sometimes services appear to start but login fails;
-   the server/client connection has **not yet been tested**, because
    the Site Server itself is not yet reliably installable and runnable.

Your task is to make the **Site Server installation deterministic and
reliable on Windows first**, while preserving the previously working
camera, HVX SDK, gate-control, video, and recognition behavior.

Do not treat this as a request for another architectural rewrite.

------------------------------------------------------------------------

# 1. Source of truth

Inspect the repository yourself before changing anything.

Compare:

-   branch `main`
-   branch `check`

Determine the exact commit(s) by which `check` diverges from `main`.

At the time this task was prepared, `check` was only one
production/deployment commit ahead of `main`. Verify that this is still
true instead of assuming it.

The system worked substantially better before the production/deployment
changes. Therefore:

> Use `main` as the behavioral baseline and `check` as the regression
> branch.

Do **not** blindly revert `check`.

Instead:

1.  identify what production changes are useful;
2.  identify what introduced regressions;
3.  retain useful server/client architecture;
4.  restore reliable Windows behavior;
5.  avoid touching working hardware code unless evidence proves it is
    involved.

------------------------------------------------------------------------

# 2. Critical rule: source first, documentation second

Do not assume existing documentation accurately represents runtime
behavior.

Trace actual code paths.

At minimum inspect:

-   `app/desktop/launch.py`
-   `app/desktop/main.py`
-   `app/desktop/setup.py`
-   `app/desktop/api.py`
-   `app/deployment.py`
-   `app/database_config.py`
-   `app/db.py`
-   `app/api_main.py`
-   `app/site_service.py`
-   `app/media_service.py`
-   `app/recognition_worker.py`
-   `app/migrations/runner.py`
-   `app/services/bootstrap.py`
-   `app/services/backup.py`
-   `app/services/hvx_client.py`
-   `app/services/media_gateway.py`
-   `app/services/mediamtx.py`
-   `app/services/recognition_runtime.py`
-   `app/services/recognition_decoder.py`
-   `app/services/alpr.py`
-   `app/infrastructure/recognition/engines/fastalpr.py`
-   `packaging/windows/Install-SmartPark.ps1`
-   `packaging/windows/Install-SmartParkServices.ps1`
-   `packaging/windows/Install-SmartParkWinService.ps1`
-   `packaging/windows/requirements-windows.txt`
-   `packaging/make_windows_kit.sh`
-   relevant deployment/startup/Windows tests.

Also inspect the complete diff between `main` and `check`.

------------------------------------------------------------------------

# 3. Do not damage the known-working hardware pipeline

Before the production changes, SmartPark could already:

-   connect to the real HVX/QY ALPR cameras;
-   communicate with the vendor SDK;
-   obtain camera images/video;
-   recognize plates;
-   control boom gates;
-   create parking sessions;
-   print/use receipts;
-   run FastALPR;
-   work on Windows.

Preserve those capabilities.

Do **not** casually rewrite:

-   `NetSDK.dll` integration;
-   HVX host/bindings;
-   gate commands;
-   camera connection logic;
-   existing ALPR algorithms;
-   MediaMTX integration;
-   receipt/session logic.

If a production change broke the startup path around those components,
fix the startup path rather than replacing the component.

------------------------------------------------------------------------

# 4. Current symptoms

A fresh Windows Site Server installation from `check` is unreliable.

The observed failure can vary between attempts:

## A. Installer failure

Installation may fail before SmartPark becomes usable.

Investigate:

-   embedded Python extraction;
-   wheel installation;
-   duplicate/incompatible wheels;
-   PySide6 runtime;
-   ONNX Runtime native DLL requirements;
-   Visual C++ runtime DLLs;
-   FFmpeg;
-   MediaMTX;
-   32-bit HVX Python runtime;
-   Pillow 32-bit;
-   NetSDK/vendor DLL discovery;
-   environment variables;
-   ProgramData creation;
-   permissions;
-   PowerShell execution;
-   scheduled task registration;
-   setup wizard launch;
-   role-specific prerequisites.

The installer must fail with a precise reason and log location, never an
ambiguous generic error.

------------------------------------------------------------------------

## B. Recognition failure

On some attempts SmartPark gets farther, but recognition does not
operate correctly.

Determine whether failure is in:

``` text
camera
  -> camera adapter / HVX host
  -> media acquisition
  -> MediaMTX or SDK JPEG path
  -> recognition decoder
  -> latest fresh frame
  -> FastALPR detector
  -> plate crop
  -> OCR
  -> consensus / visit
  -> recognition worker
  -> persistence
```

Do not classify all recognition failures as an AI/model problem.

A failed recognition worker may actually be caused by:

-   service not started;
-   wrong working directory;
-   missing environment variable;
-   model path unavailable;
-   incorrect cache directory;
-   MediaMTX not running;
-   detect path unavailable;
-   database unavailable;
-   import failure;
-   ONNX Runtime DLL failure;
-   duplicate process ownership;
-   startup race.

Determine the real failure.

------------------------------------------------------------------------

## C. Login failure

Sometimes the application reaches the login stage but login does not
work.

Trace the complete path:

``` text
desktop Login
 -> ApiClient
 -> POST /auth/login
 -> Site Service
 -> database
 -> users
 -> roles
 -> password hashing
 -> session/token
 -> /auth/me
```

Determine whether login fails because:

-   API is not running;
-   desktop is pointed at the wrong API URL;
-   wrong database is being used;
-   administrator was never created;
-   bootstrap administrator conflicts with setup administrator;
-   database migration failed;
-   setup wizard created admin in one DB while Site Service opened
    another;
-   password changed unexpectedly;
-   installer reset-admin logic overwrote credentials;
-   deployment configuration points to another DB;
-   Site Service started before final database configuration;
-   stale `deployment.json`;
-   stale `smartpark.db`;
-   partial setup from a previous failed attempt.

A login failure must not be reported simply as "invalid credentials" if
the underlying API/database is unavailable.

------------------------------------------------------------------------

# 5. Major regression area: startup orchestration

The production changes introduced several possible owners of startup.

Currently investigate this chain carefully:

``` text
Install-SmartPark.ps1
       |
       +-> Install-SmartParkServices.ps1
       |       |
       |       +-> Windows Scheduled Tasks
       |
       +-> Start-SmartPark.bat
               |
               +-> app.desktop.launch
                       |
                       +-> deployment config
                       +-> background service checks
                       +-> Site Service
                       +-> HVX host
                       +-> Media Service
                       +-> Recognition Worker
                       +-> Desktop
```

This is too easy to race or partially initialize.

Find every code path capable of starting:

-   Site Service;
-   HVX host;
-   Media Service;
-   Recognition Worker;
-   MediaMTX;
-   desktop.

Create a startup ownership table before modifying code.

There must be exactly one authoritative owner for each production
process.

------------------------------------------------------------------------

# 6. Scheduled-task failure handling

Inspect the Windows scheduled-task path carefully.

A dangerous pattern exists if code does:

``` python
if scheduled_task_exists():
    start_scheduled_task()
    wait_for_api()
```

without proving that `start_scheduled_task()` actually succeeded.

Fix this.

If Windows rejects task startup, report:

-   task name;
-   task existence;
-   last run result;
-   task state;
-   account/user;
-   executable;
-   arguments;
-   working directory;
-   relevant log;
-   Windows error.

Do not wait 60--90 seconds for an API that can never start after a known
task-start failure.

------------------------------------------------------------------------

# 7. First-run setup must be deterministic

The setup wizard currently introduced a more complicated deployment
state.

Audit:

-   `UNCONFIGURED`
-   `CONFIGURING`
-   `CONFIGURED`
-   `RECOVERY_REQUIRED`

A failed setup must not leave SmartPark looking configured.

Use transactional semantics:

``` text
UNCONFIGURED
   |
   v
CONFIGURING
   |
   +-- success --> CONFIGURED
   |
   +-- failure --> UNCONFIGURED or RECOVERY_REQUIRED
```

Only mark the deployment `CONFIGURED` after all required checks succeed.

Required Site Server checks should include at least:

-   database usable;
-   schema at expected Alembic revision;
-   admin account exists;
-   deployment identity valid;
-   Site Service can import;
-   API can start;
-   `/health/live` responds;
-   configured server port can bind.

Hardware-specific failures may be warnings during initial setup if
hardware has not yet been configured.

------------------------------------------------------------------------

# 8. Database regression: remove ambiguous runtime ownership

Inspect `app/db.py`.

It currently creates global objects at import time similar to:

``` python
engine = create_engine(settings.resolved_database_url, ...)
SessionLocal = sessionmaker(bind=engine, ...)
```

The production work also introduced runtime database selection through
deployment configuration.

This creates an initialization-order hazard.

Example:

``` text
wizard chooses candidate DB
       |
       +-> migration helper
               |
               +-> imports app.db
                       |
                       +-> creates global engine from current settings
```

while the wizard may separately be using another candidate engine.

That can cause:

-   setup writes admin to DB A;
-   Site Service opens DB B;
-   login fails;
-   migrations are checked against the wrong database;
-   tests pass while packaged Windows startup fails.

Audit this rigorously.

Refactor if necessary so that database configuration is finalized
**before** the application database engine is constructed.

Do not hot-swap a globally imported SQLAlchemy engine.

Preferred invariant:

> A Site Service process resolves one authoritative database
> configuration before importing/initializing the ORM and uses that
> database for its entire lifetime.

------------------------------------------------------------------------

# 9. SQLite must remain a reliable commissioning option

PostgreSQL can remain the recommended production database.

However, we need to stabilize SmartPark on Windows before testing
server/client deployment.

Provide an explicit mode:

### SQLite --- Testing / Commissioning

It should:

-   require no external database installation;
-   create its directory automatically;
-   create/migrate schema automatically;
-   create the initial admin;
-   run integrity/read/write checks;
-   display a clear warning that it is not the recommended
    multi-workstation production database.

It must nevertheless **work reliably**.

Do not deliberately cripple SQLite.

This is currently the fastest way to prove:

``` text
Windows installation
 -> Site Server
 -> cameras
 -> recognition
 -> login
 -> parking
```

before introducing PostgreSQL as another variable.

------------------------------------------------------------------------

# 10. PostgreSQL behavior

Keep PostgreSQL support, but do not let PostgreSQL make a fresh Windows
commissioning install unusable.

The Windows installer does not currently bundle a complete PostgreSQL
server installation.

Therefore do not imply that PostgreSQL is automatically available.

If selected, verify:

-   host reachable;
-   port reachable;
-   authentication;
-   target database;
-   permissions;
-   migrations;
-   read/write;
-   secret storage.

Provide an actionable error if PostgreSQL is absent.

Do not expose the PostgreSQL password in:

-   `deployment.json`;
-   command-line arguments;
-   logs;
-   health endpoints.

Operator Workstations must never connect directly to PostgreSQL.

------------------------------------------------------------------------

# 11. Administrator/login lifecycle must have one source of truth

There are currently multiple concepts around initial credentials:

-   setup wizard administrator;
-   bootstrap administrator;
-   `bootstrap_password.txt`;
-   installer `reset-admin`;
-   existing users.

This can easily create a login regression.

Define the lifecycle clearly.

For a fresh Site Server configured through the wizard:

1.  database is initialized;
2.  wizard creates the administrator chosen by the technician;
3.  Site Service starts against that same database;
4.  the exact chosen credentials work;
5.  installer must **not subsequently overwrite that password**;
6.  bootstrap credentials must not silently replace the wizard
    administrator.

For an existing installation:

-   preserve existing users;
-   do not reset admin password during ordinary upgrade;
-   do not create a second admin unexpectedly.

Bootstrap credentials may remain only as a clearly defined
development/recovery mechanism.

Add tests proving this.

------------------------------------------------------------------------

# 12. Installer must be idempotent

Running the installer twice should not progressively damage the
installation.

Test:

``` text
clean install
install again
repair install
failed install -> rerun
configured install -> upgrade
```

Preserve:

-   database;
-   deployment identity;
-   site settings;
-   users;
-   camera configuration;
-   gates;
-   parking data.

Do not reset credentials on every installer execution.

Do not create duplicate scheduled tasks/processes.

Do not silently wipe ProgramData.

------------------------------------------------------------------------

# 13. Partial-installation recovery

The current symptoms vary between attempts, which strongly suggests
partial state may survive failed installations.

Audit all persistent state:

``` text
%ProgramData%\SmartParkEdge\
deployment.json
smartpark.db
logs\
model-cache\
bootstrap_password.txt
secret storage
generated MediaMTX configuration
```

Also inspect:

-   scheduled tasks;
-   installed application directory;
-   environment variables;
-   running Python processes;
-   running MediaMTX processes;
-   ports;
-   firewall rules.

A failed installation must either:

1.  roll back incomplete state; or
2.  leave a clearly detectable recoverable state.

Do not let an incomplete `deployment.json` cause subsequent installers
to assume a healthy configured installation.

------------------------------------------------------------------------

# 14. Role-specific installation

The installer should not require Site Server hardware dependencies
before it knows the selected role.

## Site Server

May need:

-   64-bit Python runtime;
-   FastAPI;
-   SQLAlchemy;
-   SQLite/PostgreSQL driver;
-   FFmpeg;
-   MediaMTX;
-   FastALPR;
-   ONNX Runtime;
-   model files;
-   camera adapter;
-   32-bit HVX runtime and NetSDK **only if HVX hardware is used**;
-   printer/gate components as configured.

## Operator Workstation

Should need only:

-   desktop runtime;
-   PySide;
-   HTTP client;
-   media/WebRTC viewing requirements;
-   network access to Site Server.

It should not require:

-   FastALPR;
-   ONNX Runtime;
-   PostgreSQL;
-   SQLite application database;
-   HVX SDK;
-   NetSDK;
-   camera access;
-   gate access;
-   local recognition worker;
-   local Media Service.

Do not let a missing HVX DLL block an Operator Workstation installation.

------------------------------------------------------------------------

# 15. Recognition worker startup

Recognition previously worked. Treat the production process split as the
suspect until disproved.

Verify the worker starts with the same effective environment as the
known-working application:

-   `SMARTPARK_HOME`;
-   `PYTHONPATH`;
-   data directory;
-   deployment profile;
-   database URL;
-   model/cache path;
-   MediaMTX binary/path;
-   FFmpeg;
-   PATH;
-   working directory.

Log these **non-secret** resolved paths at startup.

Never log passwords/tokens.

Before starting inference, log/check:

``` text
deployment role
database engine
database connectivity
schema revision
recognition scope
camera count
model cache path
model availability
FFmpeg availability
MediaMTX detect endpoint
ONNX Runtime provider
worker PID
```

A worker startup failure should be obvious from one log.

------------------------------------------------------------------------

# 16. Do not multiply recognition processes

Verify that desktop startup, scheduled tasks, installer and Site Service
cannot accidentally start multiple recognition workers.

Invariant:

> One configured recognition owner per Site Server/node.

Likewise:

> One active inference pipeline per configured camera/lane, with shared
> bounded model resources where appropriate.

Duplicate recognition processes can produce:

-   model memory pressure;
-   frozen recognition;
-   duplicate parking events;
-   duplicate sessions;
-   unnecessary camera pulls.

------------------------------------------------------------------------

# 17. Preserve the recognition architecture

Do not "fix" this task by replacing the existing recognition system.

Preserve:

``` text
fresh frame
 -> detector
 -> plate crop
 -> OCR
 -> Tanzania normalization
 -> visit/consensus
 -> authoritative parking event
```

Keep latest-frame-wins semantics.

Do not introduce large frame queues.

Do not increase recognition FPS blindly.

The immediate problem is reliability of installation/process startup.

------------------------------------------------------------------------

# 18. Windows native dependency preflight

Create a deterministic preflight command/tool that can run before the
desktop.

Example intent:

``` text
SmartPark Windows Preflight

Python 64-bit ................ PASS
Application imports ......... PASS
PySide ...................... PASS
ONNX Runtime ................ PASS
FastALPR .................... PASS
FFmpeg ...................... PASS
MediaMTX .................... PASS
ProgramData writable ........ PASS
Database .................... PASS
Schema ...................... PASS
Port 8760 ................... PASS
HVX 32-bit runtime .......... PASS/WARNING
NetSDK ...................... PASS/WARNING
```

For HVX, use WARNING instead of FAIL if no HVX camera has been
configured yet.

The preflight should exit non-zero only for prerequisites that prevent
the selected role from operating.

------------------------------------------------------------------------

# 19. Add a Site Service diagnostic mode

Add or improve a command that starts the Site Service in foreground
diagnostic mode.

For example:

``` text
python -m app.site_service
```

must provide enough information to diagnose failure.

Before Uvicorn starts, report:

``` text
SmartPark Site Server
deployment config: PASS
role: SITE_SERVER
database config: PASS
database connection: PASS
schema: PASS
data directory: PASS
API bind: 0.0.0.0:8760
starting API...
```

If something fails, show the exact stage.

Do not swallow the traceback from diagnostic/manual startup.

Scheduled/background mode can log it instead.

------------------------------------------------------------------------

# 20. Logging

The Windows build must have predictable logs.

At minimum:

``` text
%ProgramData%\SmartParkEdge\logs\
    installer.log
    launch.log
    site-service.log
    site-service-launch.log
    hvx-host.log
    media-service.log
    recognition-worker.log
```

Each process should log:

-   timestamp;
-   application version/commit if available;
-   PID;
-   role;
-   startup stage;
-   failure reason.

Do not put secrets in logs.

------------------------------------------------------------------------

# 21. Improve error classification

Do not show:

``` text
Login failed
```

for every login-related problem.

Differentiate:

``` text
Cannot reach Site Server
Site Server starting
Database unavailable
Server configuration incomplete
Invalid username/password
Server identity mismatch
Unexpected server error
```

Likewise recognition UI should distinguish:

``` text
Recognition worker stopped
Camera unavailable
Media stream unavailable
Model unavailable
No fresh frame
No plate detected
OCR weak
Recognition healthy
```

This will make field troubleshooting dramatically easier.

------------------------------------------------------------------------

# 22. Startup order

Define and implement an explicit production startup order.

For a Site Server, a reasonable dependency sequence is:

``` text
1. load deployment configuration
2. resolve secrets
3. resolve authoritative database
4. verify database connectivity
5. migrate schema
6. start Site Service/API
7. verify /health/live
8. start/verify HVX host if required
9. start/verify Media Service/MediaMTX
10. start Recognition Worker
11. expose readiness
12. desktop may connect
```

Do not start recognition before its required DB/media dependencies are
ready.

Do not start multiple owners simultaneously and hope they converge.

------------------------------------------------------------------------

# 23. Liveness vs readiness

Implement/use separate semantics.

### Liveness

Process exists and HTTP server responds.

Example:

``` text
GET /health/live
```

### Readiness

Server is actually ready to operate.

Readiness should include critical dependencies such as:

-   deployment configured;
-   database reachable;
-   schema valid;
-   required internal services available.

Example:

``` text
GET /health/ready
```

Desktop should not interpret liveness alone as proof that
login/recognition is ready.

------------------------------------------------------------------------

# 24. Windows service strategy

Do not perform another large service rewrite just to satisfy
architectural purity.

First stabilize the current Windows startup.

However, document the current limitation if Scheduled Tasks use
`AtLogOn`.

Long term, parking backend processes should start after Windows boot
without requiring the operator to open the desktop.

Before converting everything to a Windows Service, verify the vendor
HVX/NetSDK runtime works correctly under the chosen service
account/session.

Reliability is more important than architectural appearance.

------------------------------------------------------------------------

# 25. Required automated tests

Add regression tests for the actual failures.

## Database/setup tests

Test:

-   fresh SQLite setup;
-   SQLite schema initialization;
-   initial admin creation;
-   login using wizard credentials;
-   rerun setup does not replace admin;
-   existing SQLite upgrade;
-   PostgreSQL configuration validation;
-   setup failure does not mark deployment configured;
-   Site Service uses the same DB configured by wizard.

## Deployment tests

Test:

-   fresh SITE_SERVER;
-   existing SITE_SERVER;
-   OPERATOR_CLIENT;
-   incomplete deployment;
-   corrupt deployment JSON;
-   recovery state.

## Windows orchestration tests

Test:

-   task missing;
-   task exists and starts;
-   task exists but Windows refuses start;
-   task starts but API exits;
-   API port already occupied by SmartPark;
-   API port occupied by unrelated process;
-   duplicate launcher;
-   recognition worker already running.

Do not mock away the result being tested.

## Login tests

Integration test:

``` text
fresh DB
 -> migrate
 -> create admin
 -> start API
 -> POST /auth/login
 -> /auth/me
```

Use the same production initialization functions.

## Recognition startup tests

Test:

-   model available;
-   model missing;
-   MediaMTX unavailable;
-   DB unavailable;
-   worker can start after dependencies become available;
-   only one worker owns recognition.

------------------------------------------------------------------------

# 26. Add a Windows smoke test

Create a script suitable for the installed Windows package.

It should verify:

``` text
deployment
database
schema
API
login capability
HVX host if configured
MediaMTX
recognition worker
model availability
camera configuration
```

It must not:

-   open the boom;
-   create real parking sessions;
-   print receipts;
-   modify production parking state.

Output both:

-   human-readable report;
-   JSON report.

------------------------------------------------------------------------

# 27. Required real Windows acceptance sequence

Do not consider this fixed only because pytest passes.

Test the actual packaged kit on a clean Windows machine/VM.

### Test A --- clean SQLite Site Server

1.  Remove previous SmartPark test installation.
2.  Install kit.
3.  Select Site Server.
4.  Select SQLite testing/commissioning.
5.  Configure admin.
6.  Finish setup.
7.  Verify API.
8.  Login.
9.  Restart SmartPark.
10. Login again.
11. Reboot Windows.
12. Verify expected services/processes return according to the currently
    supported startup model.

This must be repeatable.

### Test B --- repair/reinstall

Run installer again over the configured installation.

Verify:

-   DB preserved;
-   admin preserved;
-   deployment identity preserved;
-   no duplicate processes;
-   login still works.

### Test C --- recognition

With the existing real camera configuration:

-   HVX host starts;
-   camera connects;
-   live frames arrive;
-   recognition worker starts;
-   model loads;
-   plate recognition works.

Compare behavior against `main`.

### Test D --- failure recovery

Deliberately stop MediaMTX or Recognition Worker.

Verify the system reports the correct failure and can recover without
reinstalling SmartPark.

------------------------------------------------------------------------

# 28. Only after server is stable: test client

Do not spend time debugging client/server networking until the Site
Server passes the above acceptance tests.

After server stability is proven, use:

``` text
SERVER
IP: 192.168.1.240
API: 0.0.0.0:8760

CLIENT
IP: 192.168.1.241
API URL: http://192.168.1.240:8760
```

Then verify:

``` text
client
 -> server /health/live
 -> server identity
 -> login
 -> sessions
 -> camera live view
 -> recognition status
```

The Operator Workstation must not create a local SmartPark application
database or start recognition/hardware services.

------------------------------------------------------------------------

# 29. Do not optimize unrelated things

For this task, avoid:

-   redesigning UI;
-   retraining OCR;
-   changing tariff logic;
-   rewriting camera SDK;
-   introducing another media server;
-   changing gate protocols;
-   broad model optimization;
-   unrelated refactoring.

Fix the production regression first.

------------------------------------------------------------------------

# 30. Implementation strategy

Work in small, testable stages.

## Stage 1 --- Regression report

Before editing, produce a concise internal analysis:

``` text
main behavior
check behavior
changed startup path
changed DB path
changed login/admin path
changed recognition process path
likely regression points
```

Use actual source/diff evidence.

## Stage 2 --- Installer

Make installation deterministic.

## Stage 3 --- SQLite Site Server

Make a fresh SQLite commissioning install work end-to-end.

## Stage 4 --- Login

Prove admin creation and login.

## Stage 5 --- Recognition

Prove the existing recognition pipeline works under the new process
architecture.

## Stage 6 --- Reinstall/reboot/recovery

Prove persistence and idempotency.

## Stage 7 --- PostgreSQL

Stabilize PostgreSQL without breaking SQLite commissioning.

## Stage 8 --- Operator Workstation

Only then validate the second laptop.

Do not combine all stages into one giant speculative patch.

------------------------------------------------------------------------

# 31. Definition of done

This task is **not complete** because code looks production-ready.

It is complete when a clean Windows machine can repeatedly do:

``` text
install SmartPark
        |
        v
choose Site Server
        |
        v
choose SQLite commissioning
        |
        v
configure admin
        |
        v
finish setup
        |
        v
Site Service starts
        |
        v
login succeeds
        |
        v
camera services start
        |
        v
recognition starts
        |
        v
existing cameras recognize plates
```

without random failure between attempts.

And:

``` text
reinstall / restart / reboot
```

must not break it.

After that, PostgreSQL and the Operator Workstation can be validated.

------------------------------------------------------------------------

# 32. Final report required from Cursor

After implementing fixes, report:

## Root causes found

For every actual failure found:

``` text
Symptom:
Root cause:
Affected file/function:
Why main worked:
Why check failed:
Fix:
Regression test:
```

## Files changed

List every modified file and why.

## Startup ownership

Provide the final process ownership table.

## Database lifecycle

Explain exactly when and where the authoritative DB is selected.

## Admin/login lifecycle

Explain how the first administrator is created and why credentials
cannot be overwritten accidentally.

## Windows test results

Report actual results for:

-   clean install;
-   SQLite setup;
-   login;
-   restart;
-   reinstall;
-   recognition startup;
-   real camera test if hardware is available.

## Remaining limitations

Be explicit.

Do not claim a Windows behavior was verified if it was only mocked or
tested on Linux.

------------------------------------------------------------------------

# Final instruction

The objective is **stability before sophistication**.

The production work should make the previously working SmartPark system
easier to deploy; it must not make installation, recognition, or login
probabilistic.

Use `main` to understand the working behavior. Use `check` to identify
the production regression. Preserve the valuable deployment work, but
simplify or correct anything that prevents deterministic Windows
operation.

Do not hide failures with retries. Find and fix the underlying
initialization, dependency, database, process-ownership, or packaging
problem.
