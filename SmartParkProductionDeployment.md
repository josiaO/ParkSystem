# SmartPark Production Deployment — Second Audit and Required Corrections

Audit the **CURRENT HEAD** before making changes.

The latest production-deployment implementation has established the correct basic direction, particularly:

- `SITE_SERVER`
- `OPERATOR_CLIENT`
- `EDGE_NODE`
- deployment.json
- configurable desktop API endpoint
- operator clients not starting local parking services
- server identity verification
- role-aware Windows installer behavior

**Preserve these improvements.**

Do not rewrite the working camera, recognition, MediaMTX, HVX, parking or gate pipeline.

However, the current deployment implementation is still incomplete for a real production installation.

Your task is to finish it from the perspective of:

> A technician who receives SmartPark on a Windows installer/USB and must install a complete Site Server and one or more Operator Workstations without editing Python, `.env`, SQL, PowerShell or source code.

The technician should be guided through everything required.

---

# 1. CURRENT CRITICAL GAP

The existing `app/desktop/setup.py` is currently only a lightweight deployment selector.

It roughly handles:

```text
Welcome
→ Role
→ Server URL/site name
→ Test connection
→ Review
```

This is NOT sufficient for production.

The setup system must become the authoritative first-run deployment configurator.

Do not confuse:

```text
"deployment.json exists"
```

with:

```text
"SmartPark has been successfully configured for production"
```

A server is not configured merely because its role is `SITE_SERVER`.

---

# 2. DEPLOYMENT ROLES

Keep the conceptual separation:

```text
SITE_SERVER
OPERATOR_CLIENT
EDGE_NODE
```

For ordinary installations expose prominently:

```text
Site Server
Operator Workstation
```

Keep EDGE_NODE under advanced/distributed deployment until that topology is fully supported.

## SITE_SERVER owns

```text
Database
API
Parking business logic
Cameras
Recognition
MediaMTX
HVX SDK
Gate hardware
Printers
Evidence
Backups
Configuration
Users/authentication
```

## OPERATOR_CLIENT owns

```text
Desktop UI
local UI preferences
server connection metadata
client identity
```

It MUST NOT own:

```text
database
FastALPR
camera SDK
camera credentials
gate hardware
parking business logic
MediaMTX
Site Service
```

---

# 3. DATABASE POLICY

Implement an explicit SmartPark database policy.

## SQLite

SQLite remains supported for:

```text
development
testing
demonstrations
Camera Lab
temporary field testing
single-machine evaluation
```

The major benefit must remain:

> zero database administration.

When the technician selects SQLite, SmartPark should automatically:

```text
create data directory
create database
run schema initialization/Alembic
create required initial data
validate schema
perform read/write test
```

No SQL knowledge should be required.

But display a clear warning:

```text
SQLite — Testing / Evaluation

SmartPark can configure SQLite automatically.

SQLite is suitable for testing, demonstrations and development.
It is not recommended as the production database for a multi-workstation
SmartPark installation.

For production sites, PostgreSQL is recommended.
```

Require acknowledgment if a technician deliberately uses SQLite with a production deployment profile.

Do NOT prohibit it technically unless there is a genuine architectural reason.

We may need SQLite temporarily during field testing.

---

# 4. POSTGRESQL IS THE PRODUCTION DATABASE

For a normal production Site Server, recommend:

```text
PostgreSQL
```

The wizard should show:

```text
Database

● PostgreSQL
  Recommended for production
  Multi-user, reliable server database.

○ SQLite
  Testing / evaluation
  Automatically configured by SmartPark.
```

Do not expose SQLAlchemy terminology such as:

```text
postgresql+psycopg://...
```

to an ordinary technician.

---

# 5. DECIDE HOW POSTGRESQL IS PROVISIONED

Audit the current Windows package.

Determine whether PostgreSQL itself is bundled.

Do NOT pretend SmartPark can install PostgreSQL if it currently cannot.

Implement one of these properly:

## Option A — SmartPark-managed local PostgreSQL

If we decide to bundle/install PostgreSQL:

SmartPark installer/setup handles:

```text
installation
Windows service
database cluster
database
SmartPark DB user
random strong password
permissions
connection configuration
health check
backup tooling
```

This gives the best technician experience.

OR:

## Option B — Existing PostgreSQL

If PostgreSQL remains externally installed, wizard asks:

```text
Database Server
Port
Database Name
Username
Password
```

Defaults:

```text
Host: 127.0.0.1
Port: 5432
Database: smartpark
```

Then:

```text
[Test Connection]
```

The wizard must explain if PostgreSQL is missing.

Do not simply fail with:

```text
connection refused
```

Say:

```text
PostgreSQL could not be reached on this computer.

Install PostgreSQL or select SQLite for testing.
```

Do not automatically download software from the Internet during an offline installation unless that is an explicit supported installation mode.

---

# 6. DO NOT STORE THE POSTGRES PASSWORD IN deployment.json

`deployment.json` is intentionally non-secret.

Keep it that way.

Database credentials belong in a protected secret/config mechanism.

Investigate the existing secret infrastructure.

On Windows prefer:

```text
DPAPI
```

or another established SmartPark secret store.

Do not put database passwords in:

```text
deployment.json
logs
diagnostic exports
UI status pages
```

If an environment/config file is unavoidable for the server service, protect it with Windows ACLs and document the tradeoff.

---

# 7. DATABASE CONFIGURATION MODEL

Add a proper server database configuration abstraction.

Conceptually:

```text
DatabaseConfig

engine:
    SQLITE
    POSTGRESQL

SQLite:
    path

PostgreSQL:
    host
    port
    database
    username
    secret_reference
```

Do not spread database construction across the setup UI.

Have one database configuration/service layer responsible for:

```text
construct connection
test connection
create database where supported
run migration
health check
backup
restore
```

---

# 8. CRITICAL CURRENT TECHNICAL ISSUE: GLOBAL ENGINE

Audit `app/db.py`.

Currently:

```python
engine = create_engine(settings.resolved_database_url, ...)
SessionLocal = ...
```

is created at import time.

That can become problematic when the setup wizard changes the database configuration during the same process.

Do NOT hack around this by modifying globals unpredictably.

Design a controlled database configuration/application lifecycle.

Possible clean approach:

```text
Wizard
   ↓
validate candidate DB independently
   ↓
save configuration
   ↓
initialize/migrate candidate DB
   ↓
restart/start Site Service
   ↓
Site Service imports final DB configuration
```

The normal server process should start with one authoritative database configuration.

Avoid hot-swapping SQLAlchemy engines underneath running parking services.

---

# 9. DATABASE PREFLIGHT

For PostgreSQL perform:

```text
DNS/host resolution
TCP port check
PostgreSQL connection
authentication
database existence
permissions
schema access
transaction test
Alembic revision
write test
rollback test
```

Show technician-friendly results:

```text
PostgreSQL server       PASS
Authentication          PASS
Database                PASS
Permissions             PASS
Schema                   CURRENT
Read/write test          PASS
```

Provide technical details separately.

---

# 10. SQLITE PREFLIGHT

For SQLite check:

```text
data directory writable
database path
free disk
database opens
schema
write transaction
WAL capability
integrity_check
```

Show:

```text
SQLite database         READY
Location                C:\ProgramData\SmartParkEdge\smartpark.db
Schema                  CURRENT

⚠ Testing database — not recommended for production.
```

---

# 11. ALEMBIC

Keep Alembic as schema authority.

The current migration runner is a good foundation.

Preserve:

```text
fresh DB
pre-Alembic adoption
Alembic-managed upgrade
```

But production setup should explicitly report:

```text
Current revision
Required revision
Migration required?
Migration result
```

A client workstation must NEVER run Alembic.

Only the Site Server owns database migrations.

---

# 12. DATABASE MIGRATION SAFETY

Before upgrading an existing production database:

```text
detect current DB
stop/quiet write-producing services
create backup
verify backup
run migration
verify revision
perform sanity checks
restart services
```

If migration fails:

```text
do not start parking against unknown schema
show RECOVERY REQUIRED
preserve backup
preserve original data
```

Never silently wipe/recreate the DB.

---

# 13. EXISTING SQLITE INSTALLATION

This project already has a working real-camera installation.

Treat that data as valuable.

If existing:

```text
%ProgramData%\SmartParkEdge\smartpark.db
```

is detected, wizard should say:

```text
Existing SmartPark installation detected
```

Show:

```text
Database: SQLite
Cameras: N
Gates: N
Users: N
Sessions: N
Schema: ...
```

Offer:

```text
Keep existing SQLite database
```

or:

```text
Migrate to PostgreSQL
```

Do not force migration immediately.

---

# 14. SQLITE → POSTGRESQL MIGRATION

Implement a controlled migration tool before presenting migration as safe.

Workflow:

```text
Stop write-producing services
        ↓
SQLite backup
        ↓
Create/validate PostgreSQL target
        ↓
Alembic upgrade head
        ↓
Copy data
        ↓
Preserve PK/FK relationships
        ↓
Reset PostgreSQL sequences
        ↓
Compare row counts
        ↓
Validate critical relationships
        ↓
Test authentication
        ↓
Test cameras/gates/settings
        ↓
Switch authoritative DB config
        ↓
Start services
        ↓
Health check
```

If ANY critical verification fails:

```text
do not switch
```

The SQLite source remains untouched.

---

# 15. POSTGRESQL BACKUP IS CURRENTLY INCOMPLETE

Audit `app/services/backup.py`.

Current SQL export depends on DBAPI `iterdump()` and therefore effectively supports SQLite.

Do not advertise PostgreSQL as production-ready while backup remains SQLite-specific.

Implement database-specific backup providers.

Conceptually:

```text
BackupProvider
    SQLiteBackupProvider
    PostgreSQLBackupProvider
```

## SQLite

Use safe SQLite backup semantics.

Do not naïvely copy a live WAL database.

## PostgreSQL

Use a proper mechanism such as:

```text
pg_dump
```

with the bundled/installed PostgreSQL tooling.

Capture:

```text
exit status
stderr
backup path
timestamp
database identity
size
```

Never put the password in command-line arguments where it can be exposed in process listings.

Use appropriate PostgreSQL credential handling.

---

# 16. POSTGRESQL RESTORE

Implement proper PostgreSQL restore separately.

Do not reuse SQLite logic.

Require administrator confirmation.

Workflow:

```text
stop SmartPark writes
backup current database
validate selected backup
restore
run/verify Alembic state
health-check
restart services
```

Restore failure must leave a recoverable state.

---

# 17. DATABASE DOCUMENTATION

Create:

```text
docs/DATABASE_CONFIGURATION.md
```

This is one of the few documents that SHOULD exist because a technician may need it during deployment/recovery.

It must match actual implemented behavior.

Do not write aspirational instructions for features that do not exist.

Include:

# SmartPark Database Configuration

## Supported databases

```text
PostgreSQL — recommended production database
SQLite — testing/development/evaluation
```

## Architecture

Explain:

```text
Operator Workstation
        ↓
SmartPark API
        ↓
Site Server
        ↓
PostgreSQL
```

Explicitly state:

> Operator Workstations never connect directly to PostgreSQL.

## SQLite setup

Explain that SmartPark creates/configures it automatically.

Location.

Backup.

Restore.

Limitations.

Production warning.

## PostgreSQL setup

Document actual supported workflow:

```text
installation/provisioning
host
port
database
user
permissions
credential storage
connection testing
```

## Migration

SQLite → PostgreSQL.

## Backup

SQLite procedure.

PostgreSQL procedure.

## Restore

Both engines.

## Troubleshooting

Examples:

```text
PostgreSQL service stopped
port 5432 unavailable
authentication failed
database missing
migration pending
disk full
SQLite locked
```

## Security

Explain:

```text
PostgreSQL should normally remain local to Site Server
operator clients do not need port 5432
password storage
firewall
backup security
```

---

# 18. IMPORTANT NETWORK ARCHITECTURE

For the current topology:

```text
                    SITE SERVER
                         │
            ┌────────────┴─────────────┐
            │                          │
      SmartPark API              MediaMTX
            │                          │
            │                          │
       PostgreSQL                 WebRTC/WHEP
            │                          │
       LOCAL ONLY                     │
                                       │
                           ┌───────────┴───────────┐
                           │                       │
                    Workstation A            Workstation B
```

PostgreSQL should normally listen only where server processes require it.

If all server processes are on the same PC:

```text
PostgreSQL → localhost
```

is preferable.

Do NOT open PostgreSQL port 5432 in Windows Firewall for operator workstations.

---

# 19. SERVER FIRST-RUN WIZARD MUST BE EXPANDED

For `SITE_SERVER`, implement approximately:

```text
1 Welcome
2 System Requirements
3 Deployment Role
4 Server Network
5 Database
6 Database Verification
7 Existing Installation / Migration
8 Site Identity
9 Administrator
10 Server Components
11 Gates
12 Cameras
13 Hardware Test
14 Backup
15 Firewall
16 Review
17 Apply
18 Verification
19 Finish
```

Do not show irrelevant pages.

Use conditional wizard pages.

---

# 20. SERVER SYSTEM REQUIREMENTS PAGE

Check actual requirements.

At minimum:

```text
Windows version
64-bit environment
CPU architecture
RAM
free disk
network adapter
required Python runtime bundled
32-bit HVX runtime
NetSDK DLL
FFmpeg
MediaMTX
FastALPR model files
printer support where applicable
required ports
administrator privileges where needed
```

Classify:

```text
PASS
WARNING
FAIL
```

Example:

```text
64-bit runtime              PASS
HVX SDK runtime             PASS
MediaMTX                    PASS
Disk space                  PASS
PostgreSQL                  NOT CONFIGURED
Network                     PASS
```

---

# 21. CLIENT REQUIREMENTS PAGE

Do NOT run server prerequisite checks on a workstation.

Client requires roughly:

```text
supported Windows
desktop runtime
network adapter
server connectivity
WebRTC/media capability
disk for logs/preferences
```

It does NOT require:

```text
PostgreSQL
FastALPR
HVX SDK
NetSDK
camera access
gate hardware
```

The Windows kit should eventually support installing a lighter workstation package if practical.

At minimum the role must ensure unused components never run.

---

# 22. SERVER NETWORK PAGE

Show:

```text
Computer name
Adapter
IPv4
Subnet
API port
```

Recommend stable IP/DHCP reservation.

Explain:

```text
Operator Workstations must always be able to find this Site Server.
```

Do not silently change Windows static IP.

Server API production binding may use:

```text
0.0.0.0:8760
```

but firewall must restrict access appropriately.

---

# 23. CLIENT CONNECTION PAGE

Current direction is correct but improve it.

Provide:

```text
Server:
[ smartpark-server ]

Port:
[ 8760 ]

[Test]
```

Show:

```text
Server found             PASS
SmartPark API            PASS
Site                     <name>
Server identity          VERIFIED
Version                  compatible
Media                    available
Latency                  4 ms
```

A workstation must not finish configuration until a valid SmartPark server has been verified.

---

# 24. SERVER IDENTITY BUG/SEMANTICS AUDIT

Carefully audit:

```text
installation_id
server_id
client_id
node_id
```

The current code risks semantic confusion.

Define precisely:

```text
site_id
server_installation_id
client_installation_id
node_id
```

Only retain IDs that have distinct purposes.

A fresh workstation must store the expected SERVER/SITE identity after pairing.

Its own installation identity must remain its own identity.

Do not overwrite a client's identity with the server's installation ID merely to verify pairing.

Model this explicitly.

Example:

```text
client_installation_id = UUID for this workstation

paired_site_id = UUID from server
paired_server_id = UUID from server
```

Then validation becomes unambiguous.

Add tests.

---

# 25. ADMINISTRATOR CREATION

Current bootstrap-password behavior is useful for development/recovery but is not the final production experience.

During new Site Server setup ask:

```text
Administrator username
Full name
Password
Confirm password
```

Validate password.

Create first administrator securely.

Do not expose the generated bootstrap password as the normal production credential after successful setup.

The installer currently prints/references:

```text
bootstrap_password.txt
```

Review this behavior.

After production admin creation:

```text
bootstrap credential should no longer be the primary login
```

Handle recovery separately.

---

# 26. WINDOWS SERVICE OWNERSHIP

Current scheduled tasks are a transitional mechanism.

Audit:

```text
Install-SmartParkServices.ps1
Install-SmartParkWinService.ps1
```

For production, determine which mechanism is actually supported.

The key invariant is:

```text
Windows starts
↓
SmartPark server starts
↓
parking operates
```

without requiring an interactive operator to open the desktop.

Current tasks are `AtLogOn`.

That means parking may not start until a user logs in.

That is NOT the ideal production Site Server behavior.

Prefer genuine Windows services or startup tasks that run independently of interactive logon once verified with:

```text
HVX 32-bit host
PySide-independent backend
MediaMTX
recognition worker
```

Do not switch blindly if Windows-service behavior has not been tested with the vendor SDK.

But treat `AtLogOn` as a known production limitation until solved.

---

# 27. SERVICE ACCOUNT / HARDWARE ACCESS

Before converting HVX/gate processes to Windows services, verify whether the vendor SDK requires:

```text
interactive session
user profile
desktop session
specific DLL search path
hardware/network permissions
```

Test it.

Do not assume LocalSystem can run NetSDK correctly.

If necessary use a dedicated SmartPark service account.

Document the decision.

---

# 28. FIREWALL

Server wizard should configure or clearly validate:

```text
API 8760
MediaMTX WHEP/WebRTC signaling 8889
WebRTC ICE 8189 UDP/TCP
```

according to actual MediaMTX configuration.

Keep internal:

```text
HVX host 8765
MediaMTX control API 9997
metrics 9998
internal RTSP 8554
PostgreSQL 5432
```

unless architecture explicitly requires otherwise.

Operator Workstation should not need inbound SmartPark firewall rules for server services.

---

# 29. MEDIA ENDPOINTS

Audit remote MediaMTX URLs again.

Internal recognition:

```text
rtsp://127.0.0.1:8554/...
```

is correct.

Remote workstation cannot use:

```text
127.0.0.1
```

for server media.

Make API-generated WHEP endpoints deployment-aware.

Test from a physically separate Windows PC.

---

# 30. SITE CONFIGURATION

Server setup should allow:

```text
Site name
Timezone
Currency
Language
Plate profile
```

Use sensible defaults but do not hard-code Rock City Mall.

---

# 31. GATE/CAMERA CONFIGURATION

A technician must not finish server deployment and then be told:

```text
now edit the database
```

Use existing SmartPark UI/services to configure:

```text
Gate A
    Entry
    Exit

Gate B
    Entry
    Exit
```

and assign cameras.

Support:

```text
discover
manual add
test
```

Reuse current camera infrastructure.

Do not rewrite it.

---

# 32. HARDWARE VALIDATION

Before declaring the Site Server ready, provide safe checks:

```text
Camera connectivity
Live frame
Recognition
MediaMTX
Printer
Gate controller
```

Gate movement must require explicit confirmation.

Setup must never automatically raise a physical barrier.

---

# 33. BACKUP PAGE

For PostgreSQL production:

```text
Backup location
Schedule
Retention
Test backup
```

For SQLite testing:

```text
Backup location
manual/scheduled backup
```

Do not let a technician finish production setup without at least being warned that backups are unconfigured.

---

# 34. CONFIGURATION APPLY MUST BE TRANSACTIONAL

Do not mark:

```text
configured = true
```

before critical server configuration succeeds.

Current `save_deployment_config()` always sets:

```text
configured=True
```

That is too simplistic.

Introduce explicit state:

```text
UNCONFIGURED
CONFIGURING
CONFIGURED
RECOVERY_REQUIRED
```

Only set `CONFIGURED` after:

```text
database ready
schema ready
admin ready
server configuration written
required services configured
critical preflight passed
```

For workstation:

```text
server verified
identity stored
compatibility verified
```

---

# 35. CONFIGURATION ROLLBACK

Before changing an existing server:

```text
backup deployment config
backup DB where necessary
record existing service configuration
```

If Apply fails:

```text
restore previous configuration
```

Do not leave a real gate PC half-converted.

---

# 36. RECONFIGURATION UTILITY

Create a proper entry:

```text
SmartPark Deployment Configuration
```

available to administrators.

Normal launch:

```text
SmartPark
→ Login
```

not:

```text
SmartPark
→ Setup Wizard
```

unless unconfigured/recovery-required.

---

# 37. CLIENT DISCONNECTED EXPERIENCE

Current behavior shows a critical message and exits.

Improve this.

Provide a proper connection screen:

```text
SmartPark Site Server unavailable

Server:
smartpark-server:8760

Last connected:
...

[Retry]
[Diagnostics]
[Change Server]
[Exit]
```

Allow automatic retry.

Do not start a local server.

---

# 38. RUNTIME RECONNECTION

If server disappears while the workstation is open:

```text
SERVER DISCONNECTED
```

Disable state-changing operations.

Keep UI alive.

Reconnect with bounded backoff.

After recovery:

```text
SERVER CONNECTED
```

refresh authoritative state.

---

# 39. SERVER HEALTH

Create/extend health reporting so technician can see:

```text
Database             HEALTHY
Schema               CURRENT
Site Service         HEALTHY
MediaMTX             HEALTHY
Recognition          HEALTHY
HVX Host             HEALTHY
Disk                 HEALTHY
Backup               HEALTHY/WARNING

Gate A Entry          HEALTHY
Gate A Exit           HEALTHY
Gate B Entry          HEALTHY
Gate B Exit           HEALTHY
```

One camera failing should produce:

```text
DEGRADED
```

not make the entire server appear dead.

---

# 40. DATABASE HEALTH ENDPOINT

Expose safe database metadata:

```text
engine: PostgreSQL
state: HEALTHY
revision: ...
head: ...
latency_ms: ...
```

Never expose:

```text
password
full credential-bearing URL
```

Operator/technician UI should be able to determine database health without opening SQL tools.

---

# 41. CLIENT MUST HAVE ZERO DB KNOWLEDGE

Add tests proving an `OPERATOR_CLIENT`:

```text
does not import/initialize production DB during startup
does not run ensure_schema
does not run Alembic
does not require SMARTPARK_DATABASE_URL
does not require psycopg connection
```

The workstation package may contain SQLAlchemy code because the same codebase is packaged, but the client startup path must not initialize the production database.

---

# 42. IMPORTANT IMPORT-TIME AUDIT

Search the desktop import graph.

Ensure importing:

```text
app.desktop.*
```

on an OPERATOR_CLIENT does not indirectly import:

```text
app.db.engine
```

and create a local SQLite database merely because a module was imported.

This is easy to miss.

Test:

```text
fresh workstation
no smartpark.db
launch OPERATOR_CLIENT
```

After startup:

```text
smartpark.db must NOT have been created
```

This should be an automated test.

---

# 43. CLIENT PACKAGE PREREQUISITES

Audit Windows packaging.

A workstation should not fail installation because:

```text
32-bit HVX runtime missing
NetSDK DLL check fails
FastALPR model unavailable
```

Those are server requirements.

Currently the installer performs vendor runtime checks before role selection.

Refactor installation so client installation does not require server-only hardware/runtime components.

Possible approaches:

```text
common package
server feature package
```

or role-aware prerequisite installation.

Do not force every office workstation to carry/test the camera SDK.

---

# 44. SERVER PACKAGE PREREQUISITES

Conversely, Site Server must verify everything it actually needs.

For this installation:

```text
Python 64
Python 32 HVX host
NetSDK
FFmpeg
MediaMTX
FastALPR/model
camera network
database
```

If HVX cameras are configured.

Do not fail a future server using only generic RTSP cameras because an unused HVX DLL is absent.

Requirements should follow configured hardware capabilities.

---

# 45. INSTALLER ROLE TIMING

Current installer must decide some server/client requirements before the first-run wizard has selected a role.

Resolve this cleanly.

Possible production flow:

```text
Install common SmartPark files
        ↓
Launch Deployment Configuration
        ↓
Choose role
        ↓
Install/validate role-specific components
```

Do not perform mandatory HVX/server checks before discovering that this PC is only an Operator Workstation.

---

# 46. DATABASE DOCUMENTATION MUST BE INSTALLED

Include:

```text
docs/DATABASE_CONFIGURATION.md
```

in the Windows kit/documentation output.

Also make it accessible from:

```text
Help → Deployment Documentation
```

or equivalent technician-facing area.

Do not clutter normal operator workflow.

---

# 47. TECHNICIAN DEPLOYMENT DOCUMENT

Also create:

```text
docs/DEPLOYMENT.md
```

Keep it concise and practical.

Include two procedures.

## Install Site Server

```text
1. Install SmartPark
2. Select Site Server
3. Run prerequisite checks
4. Configure network
5. Select PostgreSQL
6. Configure/test database
7. Create administrator
8. Configure site
9. Configure gates/cameras
10. Verify hardware
11. Configure backup
12. Apply
13. Run acceptance test
```

## Install Operator Workstation

```text
1. Install SmartPark
2. Select Operator Workstation
3. Enter/find Site Server
4. Test
5. Verify site identity
6. Finish
7. Login
```

Include required firewall/network ports.

---

# 48. TESTING

Add comprehensive tests.

## Deployment configuration

Test all states:

```text
UNCONFIGURED
CONFIGURING
CONFIGURED
RECOVERY_REQUIRED
```

## SQLite

Test:

```text
automatic creation
Alembic head
read/write
warning classification
existing DB
corrupt DB
```

## PostgreSQL

Where CI supports it:

```text
connect
fresh schema
migration
write
backup
restore
```

If PostgreSQL integration cannot run in CI, separate integration tests clearly.

Do not fake passing PostgreSQL tests.

## Client

Test:

```text
no DB created
no schema migration
no HVX
no recognition
no MediaMTX
no Site Service
```

## Server

Test:

```text
services enabled
database required
schema checked
```

---

# 49. TWO-PC ACCEPTANCE TEST

This is mandatory before calling the deployment production-ready.

Use:

```text
PC A = Site Server
PC B = Operator Workstation
```

Test:

```text
install PC A
configure server
database
cameras
recognition
gate
```

Then:

```text
install PC B
select Operator Workstation
connect PC A
login
view cameras
view sessions
view recognition
```

Verify:

```text
PC B has no local smartpark.db
PC B has no FastALPR worker
PC B has no HVX host
PC B has no MediaMTX server
PC B has no camera connection
```

---

# 50. FAILURE ACCEPTANCE TEST

Disconnect workstation network.

Expected:

```text
workstation → disconnected
server → unaffected
parking → continues
recognition → continues
```

Reconnect.

Expected:

```text
workstation reconnects
```

Close workstation.

Expected:

```text
parking continues
```

Reboot Site Server.

Expected after supported startup mechanism:

```text
database starts
services start
cameras reconnect
recognition resumes
parking becomes operational
```

without manually launching the desktop.

---

# 51. DO NOT DESTABILIZE THE CURRENT CAMERA PIPELINE

This requirement remains absolute.

Current real-camera performance has already reached a useful baseline.

Deployment work must not rewrite:

```text
media_gateway
HVX acquisition
recognition runtime
FastALPR
entry/exit controllers
gate control
```

unless required by a specific deployment boundary.

After changes rerun the real-camera soak test.

Compare:

```text
before
after
```

for:

```text
CPU
RAM
video freezes
recognition latency
decoder restarts
duplicate sessions
```

---

# 52. REQUIRED FINAL ARCHITECTURE

Production should end approximately here:

```text
                       SMARTPARK SITE
                             │
                  ┌──────────┴───────────┐
                  │                      │
             SITE SERVER             CAMERAS/GATES
                  │
        ┌─────────┼──────────┐
        │         │          │
        ▼         ▼          ▼
 PostgreSQL   Parking     MediaMTX
              Engine         │
                │            │
             FastALPR        │
                │            │
             HVX/Gate        │
                             │
             ───────── LAN ──┼────────
                             │
                    WebRTC + API
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
        OPERATOR WORKSTATION     OPERATOR WORKSTATION
                 │                       │
              PySide                   PySide
                 │                       │
                 └──── NO DATABASE ──────┘
```

---

# 53. PRODUCT RULE

A technician should never need to ask:

> What do I put in `.env`?

or:

> Where do I create the database?

or:

> Which Python command starts the server?

or:

> Does this client need PostgreSQL?

The application should answer those questions through setup, diagnostics and documentation.

The intended experience is:

## Production Site Server

```text
Install
→ Site Server
→ prerequisites
→ PostgreSQL
→ configure/test
→ site/admin/hardware
→ backup
→ apply
→ operational
```

## Test Server

```text
Install
→ Site Server
→ SQLite
→ warning
→ SmartPark configures DB automatically
→ operational
```

## Workstation

```text
Install
→ Operator Workstation
→ server address
→ test
→ pair
→ login
```

Nothing more should be required for a normal workstation.

---

# 54. FINAL REPORT

After implementing, report honestly:

### Completed

List actual implemented items.

### Remaining production limitations

List anything still requiring manual technician work.

### Database

Report:

```text
SQLite status
PostgreSQL status
migration status
backup status
restore status
Alembic revision
```

### Server

Report prerequisites and service startup behavior.

### Client

Prove it has no database/hardware/recognition ownership.

### Physical validation

Do NOT say two-PC or real-gate testing passed unless it was actually performed.

### Files changed

List every changed file and purpose.

### Documentation

Confirm:

```text
docs/DATABASE_CONFIGURATION.md
docs/DEPLOYMENT.md
```

match the actual implementation.

### Rollback

Explain how the current working real-gate installation can be restored if the deployment changes cause a regression.

The objective is not merely to add more setup screens.

The objective is to make SmartPark **installable, understandable, recoverable and maintainable as a real production Windows parking system by a technician other than its developer.**
