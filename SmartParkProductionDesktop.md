# SmartPark — Production Desktop Deployment, Server/Client Architecture & First-Run Configuration

You are working on the **CURRENT SmartPark/ParkSystem repository**.

SmartPark has now been running against the real parking-gate cameras for approximately an hour on a normal Core i7 laptop with only occasional minor video stalls and no serious stability failure.

That working installation is valuable.

**DO NOT destabilize the working camera/recognition/gate pipeline.**

The next task is to turn SmartPark from a development-style desktop installation into a **professionally deployable Windows client/server application**.

We now want:

```text
PC 1 = SMARTPARK SITE SERVER
PC 2 = SMARTPARK OPERATOR CLIENT
```

and potentially more clients later.

The software must behave like professional Windows business software:

```text
Install
   ↓
First-run configuration
   ↓
Deployment role selection
   ↓
System checks
   ↓
Server/client configuration
   ↓
Connectivity/database/service checks
   ↓
Administrator setup
   ↓
Configuration summary
   ↓
Apply
   ↓
Start SmartPark
```

The setup wizard must NOT appear every time SmartPark starts.

Once configuration succeeds, normal launches should go directly to:

```text
SmartPark startup
   ↓
server/client health validation
   ↓
login
   ↓
operator desktop
```

The setup wizard should only return when:

- installation is genuinely unconfigured;
- an administrator explicitly opens deployment configuration;
- configuration is corrupted/incomplete;
- a controlled recovery/reconfiguration operation requires it.

---

# 1. AUDIT CURRENT SOURCE BEFORE IMPLEMENTING

Do NOT begin from this prompt alone.

Inspect the current source code.

At minimum audit:

```text
app/config.py
app/db.py
app/site_service.py
app/media_service.py
app/recognition_worker.py

app/desktop/
    launch.py
    api.py
    main.py
    shell.py
    live_cameras.py
    live_pane.py
    streams.py
    video.py

app/services/
    bootstrap.py
    node_scope.py
    health.py
    diagnostics.py
    runtime.py
    mediamtx.py
    mediamtx_sources.py
    media_gateway.py
    recognition_runtime.py
    backup.py

app/infrastructure/

app/migrations/

packaging/
packaging/windows/

config/

tests/
```

Also trace:

- authentication;
- users/roles/permissions;
- API exposure;
- MediaMTX;
- WHEP/WebRTC;
- camera ownership;
- vendor HVX SDK;
- RTSP cameras;
- recognition ownership;
- evidence/media paths;
- database access;
- migrations;
- startup;
- shutdown;
- Windows services;
- logging;
- backups;
- desktop packaging;
- firewall requirements.

**Current source code is authoritative.**

Do not rely on old project documentation.

---

# 2. IMPORTANT CURRENT ARCHITECTURE FINDINGS

Verify these against current HEAD before changing them.

The current repository already contains:

```text
Settings.node_role = SERVER | CLIENT
node_id
recognition_gate_id
PostgreSQL support
Alembic migrations
Site Service
Media Service
Recognition Worker
MediaMTX
HVX SDK Host
PySide6 desktop
Windows packaging/service scripts
```

However, the current concepts need to be corrected for a professional deployment.

## Current problem 1

`app/desktop/api.py` currently effectively assumes:

```text
BASE = http://127.0.0.1:8760
```

Therefore the desktop assumes its API is on the same machine.

That must become configurable.

---

## Current problem 2

`app/desktop/launch.py` currently starts:

```text
HVX SDK Host
Site Service
Media Service
Recognition Worker
```

before launching the desktop.

That is appropriate for a standalone/server installation.

It is WRONG for a pure operator client.

A workstation client must NOT start:

```text
HVX host
camera acquisition
MediaMTX
recognition worker
site service
local parking database
gate hardware control
```

unless it has explicitly been configured as a server/edge node.

---

## Current problem 3

The existing `CLIENT` topology in `config.py` currently requires things such as:

```text
PostgreSQL database URL
recognition_gate_id
shared_media_dir
```

This represents something closer to a:

```text
LANE PROCESSING NODE
or
EDGE GATE NODE
```

than an ordinary desktop operator client.

Do NOT keep conflating these concepts.

---

# 3. DEFINE CLEAR DEPLOYMENT ROLES

Create explicit deployment concepts.

At minimum:

```text
SITE_SERVER
OPERATOR_CLIENT
```

Optionally preserve/refactor the existing distributed lane concept into:

```text
EDGE_NODE
```

if current source requires it.

Conceptually:

```text
SITE_SERVER
    owns authoritative database
    owns API
    owns cameras
    owns MediaMTX
    owns recognition
    owns vendor SDK
    owns parking engine
    owns gate control
    owns receipts/payment backend
    owns evidence
    owns backups
```

```text
OPERATOR_CLIENT
    owns desktop UI only
    authenticates to Site Server
    calls Site Server API
    displays server-provided live video
    performs authorized operator commands through API
    NEVER directly opens database
    NEVER directly controls camera
    NEVER directly controls gate
    NEVER runs FastALPR
```

Optional:

```text
EDGE_NODE
    specialized distributed processing machine
    assigned to physical gate
    may own cameras/recognition/hardware for that gate
```

Do not expose EDGE_NODE in the ordinary setup wizard unless it is actually ready for production.

---

# 4. TARGET PRODUCTION TOPOLOGY

For the current Rock City deployment, the target should be approximately:

```text
                         SITE SERVER
                    ┌────────────────────┐
                    │ SmartPark API      │
                    │ Database           │
                    │ MediaMTX           │
                    │ Recognition Worker │
                    │ FastALPR           │
                    │ HVX SDK Host       │
                    │ Parking Engine     │
                    │ Gate Control       │
                    │ Evidence           │
                    │ Backup             │
                    └─────────┬──────────┘
                              │
                         LAN / FIBER
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
      Operator Client 1               Operator Client 2
      ┌───────────────┐               ┌───────────────┐
      │ PySide Desktop│               │ PySide Desktop│
      │ API Client    │               │ API Client    │
      │ WebRTC viewer │               │ WebRTC viewer │
      └───────────────┘               └───────────────┘
```

Physical cameras communicate with the server.

Operator clients communicate with SmartPark, not directly with cameras.

---

# 5. CLIENT MUST NEVER CONNECT DIRECTLY TO THE DATABASE

This is mandatory.

Do NOT design:

```text
Client
   ↓
PostgreSQL
```

for ordinary operator workstations.

Use:

```text
Client
   ↓
SmartPark API
   ↓
business/service layer
   ↓
database
```

The client must not know:

```text
database password
database username
database port
database schema
```

The server is the database authority.

This provides:

- security;
- business-rule enforcement;
- centralized auditing;
- simpler upgrades;
- less database corruption risk;
- cleaner permissions;
- easier future mobile/web clients.

---

# 6. FIRST-RUN STATE MACHINE

Implement an explicit installation/deployment state.

Do not infer setup completion from random `.env` fields.

Use something conceptually similar to:

```text
UNCONFIGURED
CONFIGURING
CONFIGURED
RECOVERY_REQUIRED
```

Persist configuration safely in the appropriate Windows application data directory.

For example:

```text
C:\ProgramData\SmartPark\
```

following the project's existing data-directory conventions.

Store:

```text
deployment role
server identity
server URL
site identity
machine/node identity
configuration version
setup completion
installation ID
```

Do not store plaintext sensitive secrets unnecessarily.

---

# 7. STARTUP ROUTER

Change application startup conceptually to:

```text
SmartPark.exe
      ↓
Load local deployment configuration
      ↓
Is installation configured?
   NO ─────→ Setup Wizard
   YES
      ↓
Which role?
 ┌───────────────┬─────────────────┐
 │ SITE_SERVER   │ OPERATOR_CLIENT │
 └──────┬────────┴────────┬────────┘
        │                 │
        ▼                 ▼
 server checks       server discovery/check
        │                 │
 server services       API reachable?
        │                 │
        ▼                 ▼
      Login             Login
        │                 │
        └───────┬─────────┘
                ▼
         SmartPark Desktop
```

Do not show the normal desktop behind the setup wizard.

First-run setup should feel like installation/configuration, not an ordinary Settings page.

---

# 8. PROFESSIONAL FIRST-RUN SETUP WIZARD

Create a native PySide6 setup wizard consistent with SmartPark styling.

Use appropriate desktop wizard conventions.

Do not make one giant form.

Use sequential pages.

Suggested flow:

---

## PAGE 1 — Welcome

Display:

```text
SmartPark Setup

This wizard will configure this computer for your parking site.
```

Show:

```text
SmartPark version
computer name
Windows version
network status
```

Buttons:

```text
Cancel
Next
```

---

# 9. PAGE 2 — DEPLOYMENT ROLE

Ask:

> How will this computer be used?

Large choices:

### Site Server

Description:

```text
Runs the central SmartPark services and manages
the database, cameras, recognition, gates and connected clients.
```

### Operator Workstation

Description:

```text
Connects to an existing SmartPark Site Server
for monitoring and authorized parking operations.
```

Do NOT call the second option simply "Client" in the UI if "Operator Workstation" is clearer.

If EDGE_NODE exists, put it under:

```text
Advanced deployment
```

not next to normal choices unless required.

---

# 10. SERVER SETUP — SYSTEM PRE-FLIGHT

If SITE_SERVER is selected, run checks.

Display each check professionally:

```text
✓ Windows supported
✓ 64-bit runtime
✓ Installation directory
✓ Data directory writable
✓ Required ports available
✓ Network adapter detected
✓ MediaMTX available
✓ FFmpeg available
✓ FastALPR dependencies
✓ HVX 32-bit runtime
✓ NetSDK available
✓ Disk capacity
✓ Database engine
✓ Firewall capability
```

Use:

```text
PASS
WARNING
FAIL
```

A warning can continue when safe.

A critical failure cannot.

Provide:

```text
Retry
Details
```

Do not dump Python stack traces into the normal wizard.

Put technical details behind `Details`.

---

# 11. SERVER NETWORK CONFIGURATION

Show available LAN interfaces.

Display:

```text
Computer name
IPv4 address
Subnet
Adapter
```

The server should preferably have a stable LAN address.

Do NOT silently configure a static Windows IP unless explicitly supported and confirmed.

If DHCP is being used, warn:

```text
This server currently uses an address that may change.

SmartPark clients need a stable server address.
Configure a DHCP reservation or static LAN address.
```

Where practical support hostname:

```text
smartpark-server
```

in addition to IP.

Do not rely exclusively on mDNS if Windows/LAN reliability is uncertain.

---

# 12. SERVER API BINDING

The current default:

```text
127.0.0.1:8760
```

is correct for local-only development but not for LAN clients.

SITE_SERVER production configuration must bind the required server interface.

Conceptually:

```text
0.0.0.0:8760
```

or selected interface.

Do not expose SmartPark unnecessarily to public interfaces.

Firewall rules should be scoped appropriately to:

```text
Private/Domain network
LAN subnet
```

not unrestricted Internet exposure.

---

# 13. DATABASE CONFIGURATION

This requires serious treatment.

The current repository supports:

```text
SQLite
PostgreSQL
```

and uses Alembic.

Audit actual database behavior before changing anything.

## Production recommendation

For a professional Site Server, prefer:

```text
PostgreSQL
```

particularly as SmartPark grows.

However:

**DO NOT destroy or automatically replace the currently working SQLite installation.**

The existing working site may contain real:

```text
cameras
gates
users
sessions
settings
recognitions
payments
```

Build a safe migration path.

---

# 14. DATABASE WIZARD

For new server installation provide choices appropriate to implementation maturity.

Preferred:

```text
Recommended
○ PostgreSQL — production

Advanced/testing
○ SQLite — single-server/local installation
```

If PostgreSQL is bundled/installed by SmartPark, implement it properly.

If not, detect an existing PostgreSQL installation or provide clear installation/configuration handling.

Do not fake PostgreSQL provisioning.

---

# 15. DATABASE CHECKS

Before accepting database configuration test:

```text
server reachable
port reachable
credentials valid
database exists
schema compatible
migration status
write permission
transaction works
current Alembic revision
latest Alembic revision
```

Display:

```text
Database connection       PASS
Authentication            PASS
Schema                    PASS
Migration                 CURRENT
Write test                PASS
```

Never expose database passwords in logs.

---

# 16. EXISTING SQLITE → POSTGRESQL MIGRATION

Because the current real installation may already contain data, implement or prepare a controlled migration mechanism.

Before migration:

```text
STOP write-producing SmartPark services
create backup
verify backup
record row counts
```

Then:

```text
create PostgreSQL schema
Alembic upgrade head
copy data transactionally
preserve IDs/relationships
verify counts
verify critical relationships
verify users
verify cameras/gates
verify settings
verify sessions
```

Only switch configuration after verification succeeds.

If migration fails:

```text
keep original SQLite untouched
restore previous configuration
restart previous deployment
```

Never delete the source database automatically.

---

# 17. BACKUP BEFORE DANGEROUS CONFIGURATION

Before:

```text
database migration
deployment-role conversion
major configuration reset
```

create a backup.

Use the existing backup infrastructure where suitable.

A production configuration wizard must not gamble with live parking data.

---

# 18. SITE IDENTITY

Server wizard should configure:

```text
Site name
Site timezone
Currency
Locale/language
```

For this installation sensible values may be selected by the administrator, but do not hard-code Rock City Mall into the product.

The product should remain reusable.

---

# 19. INITIAL ADMINISTRATOR

Current bootstrap behavior generates an install password.

For production first-run setup, improve this.

Wizard should require:

```text
Administrator username
Full name
Password
Confirm password
```

Enforce password policy.

Do not leave a known/default production admin password.

Bootstrap password generation can remain as recovery/development infrastructure if needed, but completed production setup should have an administrator-selected credential.

Never display the password again after completion.

---

# 20. SERVER SERVICES

After configuration, server mode should own the appropriate processes/services.

Audit and professionalize:

```text
SmartPark Site Service
SmartPark Media Service
SmartPark Recognition Worker
HVX SDK Host
MediaMTX
```

Prefer proper Windows service ownership for server components.

The desktop UI must NOT be required for parking operation.

Invariant:

> Closing SmartPark Desktop must not stop parking recognition, sessions or automatic gate operation on the Site Server.

This is critical.

---

# 21. WINDOWS SERVICE STARTUP

Server services should:

```text
start with Windows
restart after failure
log failure
run without an operator logged in
```

Use the existing Windows service packaging infrastructure where appropriate.

Do not create duplicate service managers.

Verify:

```text
Windows boot
 ↓
SmartPark services start
 ↓
database ready
 ↓
media ready
 ↓
recognition ready
 ↓
cameras reconnect
 ↓
parking operational
```

without opening the desktop application.

---

# 22. SERVICE DEPENDENCY ORDER

Do not rely on arbitrary sleep values.

Model readiness.

Conceptually:

```text
database
   ↓
Site Service
   ↓
Media Service / MediaMTX
   ↓
Recognition Worker
   ↓
camera/parking readiness
```

Components should tolerate temporary dependency failure and retry with bounded backoff.

Example:

```text
PostgreSQL not ready
→ Site Service WAITING
→ retry
→ PostgreSQL available
→ continue
```

---

# 23. CAMERA CONFIGURATION

After core server setup, configure cameras.

Reuse the current camera onboarding/discovery functionality.

Wizard should support:

```text
Discover cameras
Add manually
Test connection
```

For each camera:

```text
Name
IP/host
Camera type/adapter
Username
Password
Gate
Direction
Stream
Enabled
```

Camera types may include:

```text
HVX/vendor
Hikvision
Dahua
Generic RTSP/ONVIF
```

based on actual supported adapters.

---

# 24. CAMERA CREDENTIAL SECURITY

Do not store camera passwords in plaintext configuration.

Use the project's existing secret backend.

On Windows prefer DPAPI or another existing secure implementation.

Logs must redact:

```text
camera password
RTSP credentials
database password
API credentials
payment secrets
```

---

# 25. GATE TOPOLOGY

Wizard should allow defining:

```text
Site
  ├── Gate A
  │     ├── ENTRY
  │     └── EXIT
  │
  └── Gate B
        ├── ENTRY
        └── EXIT
```

Associate:

```text
camera
gate
direction
gate hardware
printer if applicable
```

Do not make operators manually edit `.env` to define topology.

---

# 26. HARDWARE TEST PAGE

Before completing setup provide safe tests:

```text
Camera reachable
Live video available
Recognition available
Gate controller reachable
Printer reachable
MediaMTX healthy
```

Manual gate testing must require explicit administrator confirmation.

Never automatically open a physical barrier merely because setup is running.

---

# 27. SERVER LIVE VIDEO FOR CLIENTS

Operator clients must be able to see live cameras through the server.

Target:

```text
Camera
   ↓
Server MediaMTX
   ↓
WebRTC/WHEP
   ↓
Operator Client
```

Do not make every client open another upstream connection directly to the physical camera.

This protects camera resources.

---

# 28. MEDIA URL CORRECTION

Audit current MediaMTX endpoint generation carefully.

Internal server consumers can use:

```text
rtsp://127.0.0.1:8554/...
```

But remote clients cannot use server `127.0.0.1`.

Server API must provide or derive browser/client-reachable media endpoints.

Example:

```text
http://SMARTPARK-SERVER:8889/cam1/whep
```

or appropriate server IP.

Do not store an unnecessarily rigid server IP inside every camera row.

Use deployment/network configuration to construct external media URLs.

---

# 29. CLIENT FIRST-RUN WIZARD

When OPERATOR_WORKSTATION is selected, DO NOT ask for:

```text
database URL
PostgreSQL password
camera passwords
recognition gate
shared filesystem
HVX SDK
FastALPR settings
```

Those are server concerns.

Client setup should be simple.

---

# 30. CLIENT SERVER DISCOVERY

Provide:

```text
Find SmartPark Server
```

where reliable.

Investigate safe LAN discovery.

Do not depend solely on discovery.

Always support:

```text
Server hostname/IP:
[ smartpark-server                ]

Port:
[ 8760 ]

[Test Connection]
```

Possible future discovery can use a constrained LAN mechanism.

Do not aggressively scan the entire network.

---

# 31. TEST SERVER CONNECTION

Client setup must verify:

```text
DNS/hostname resolution
TCP connectivity
SmartPark API reachable
API identifies itself as SmartPark
server version
API compatibility
site identity
server health
authentication available
media capability
```

Display something like:

```text
Server:       SMARTPARK-SERVER
Site:         Rock City Mall
Address:      192.168.x.x
Version:      0.x.x
API:          Connected
Media:        Available
Status:       Ready
```

Do not treat "port opened" as sufficient proof.

---

# 32. PREVENT CONNECTING TO WRONG SERVER

Implement a server identity.

For example:

```text
installation/site UUID
site name
server ID
API version
application version
```

After initial pairing, remember the expected server identity.

If later the same IP points to a different SmartPark installation:

```text
Server identity changed.
```

Do not silently trust it.

This protects against DHCP/IP reuse and configuration mistakes.

---

# 33. CLIENT CONFIGURATION

Persist locally:

```text
role = OPERATOR_CLIENT
server URL
expected server/site ID
client installation ID
display preferences
```

Do NOT copy:

```text
server database
camera credentials
gate credentials
payment provider secrets
```

to the workstation.

---

# 34. REFACTOR API CLIENT

Remove the hard-coded assumption:

```python
BASE = "http://127.0.0.1:8760"
```

Replace it with a properly configured server endpoint.

Conceptually:

```text
deployment_config.server_base_url
```

Every API request should use the configured endpoint.

Centralize:

```text
timeouts
authentication
base URL
retry policy
error handling
connection state
```

Do not scatter server URLs throughout the UI.

---

# 35. CLIENT LAUNCHER

This is critical.

Currently the desktop launcher starts local backend services.

Refactor startup based on deployment role.

### SITE_SERVER

May:

```text
verify Windows services
start/recover local service if required
connect desktop to localhost/server API
```

### OPERATOR_CLIENT

Must:

```text
NOT start HVX SDK Host
NOT start Site Service
NOT start Media Service
NOT start recognition worker
NOT start MediaMTX
NOT initialize local parking database
```

Instead:

```text
load server address
      ↓
connect
      ↓
health/version check
      ↓
login
      ↓
desktop
```

---

# 36. CLIENT OFFLINE BEHAVIOR

If the server is unavailable, do not crash and do not start a fake local server.

Show:

```text
Cannot connect to SmartPark Site Server

Server: smartpark-server
Last successful connection: ...
```

Actions:

```text
Retry
Network Diagnostics
Change Server
Exit
```

Do not allow normal parking operations using stale data.

---

# 37. CONNECTION LOSS WHILE RUNNING

If client loses server connection:

```text
desktop remains open
```

but clearly enters:

```text
SERVER DISCONNECTED
```

Disable dangerous actions.

Retry in background with bounded backoff.

When connection returns:

```text
SERVER CONNECTED
```

refresh authoritative state.

Do not require restarting the client.

---

# 38. IMPORTANT SERVER INDEPENDENCE

If every operator workstation is turned off:

```text
SERVER MUST KEEP OPERATING.
```

Recognition continues.

Entry continues.

Exit continues.

Sessions continue.

Gate automation continues.

Payments continue.

The client is a control/monitoring surface, not part of the critical parking pipeline.

---

# 39. AUTHENTICATION

Each operator must log in using the existing SmartPark account system.

Do not create a shared client-machine password as a replacement for user authentication.

Client:

```text
connect server
   ↓
login
   ↓
receive token/session
   ↓
permissions
   ↓
desktop
```

Respect existing roles and permissions.

---

# 40. SECURITY

This is a LAN system but still treat it professionally.

At minimum:

- authenticate all privileged API operations;
- never expose DB directly to operator clients;
- redact secrets;
- scope Windows firewall rules;
- do not expose MediaMTX control API;
- do not expose PostgreSQL unnecessarily;
- keep MediaMTX RTSP/control/metrics internal where appropriate;
- expose only required WebRTC/WHEP ports;
- protect configuration changes with administrator permission;
- log administrative configuration changes;
- prevent ordinary operators changing deployment topology.

Design a clean path for future HTTPS/TLS.

Do not introduce a fake self-signed TLS system that causes more operational problems unless implemented correctly.

---

# 41. VERSION COMPATIBILITY

Server should expose:

```text
application version
API protocol version
schema/migration state
```

Client checks compatibility.

Examples:

```text
Client 1.2
Server 1.2
→ compatible
```

```text
Client requires API 4
Server provides API 2
→ update required
```

Do not let incompatible client/server versions fail randomly later.

---

# 42. DATABASE SCHEMA OWNERSHIP

Only the server should perform production schema migrations.

A workstation must NEVER run:

```text
ensure_schema()
Alembic upgrade
```

against the server.

Server startup/setup owns migrations.

Use locking/coordination so two server processes cannot race a migration.

---

# 43. SINGLE SERVER AUTHORITY

Prevent accidental double-server operation against the same physical site.

A second workstation configured as OPERATOR_CLIENT must not suddenly start:

```text
recognition
camera SDK
gate commands
```

locally.

Where feasible add deployment/server identity checks to reduce accidental duplicate ownership.

---

# 44. EDGE NODE IS DIFFERENT FROM OPERATOR CLIENT

Preserve this architectural distinction.

Future deployment may become:

```text
Central Server
    │
    ├── Gate A Edge Node
    ├── Gate B Edge Node
    ├── Operator Client
    └── Operator Client
```

An EDGE_NODE may legitimately have:

```text
gate assignment
camera access
recognition
hardware
```

An OPERATOR_CLIENT must not.

Refactor current `node_role=CLIENT` semantics carefully rather than silently changing behavior and breaking existing tests.

Use migrations/compatibility mapping where needed.

---

# 45. SERVER MANAGEMENT PAGE

After setup, administrators should have:

```text
Settings
   → Deployment
```

or equivalent.

Show:

```text
Role: Site Server
Server ID
Site
Hostname
LAN address
API status
Database status
Database type
Schema version
Media status
Recognition status
Connected clients
Application version
Last backup
```

Do not show database password.

---

# 46. CLIENT MANAGEMENT PAGE

On workstation:

```text
Settings
   → Connection
```

Show:

```text
Role: Operator Workstation
Site
Server
Server ID
Connection
Latency
Server version
Client version
Media status
Last connected
```

Actions:

```text
Test Connection
Reconnect
Network Diagnostics
Change Server
```

Changing server must require appropriate confirmation/admin rights.

---

# 47. CONNECTED CLIENTS

Server should track useful client presence.

Do not build invasive surveillance.

Useful fields:

```text
client installation ID
computer name
logged-in user
client version
last seen
connection status
```

Allow administrator to understand:

```text
Control Room PC      online
Gate Office PC       online
Manager PC           offline
```

Use heartbeat/session mechanisms appropriately.

---

# 48. DO NOT USE CLIENT HEARTBEAT FOR PARKING AUTHORITY

Client disconnecting must never affect:

```text
camera
recognition
parking
gate
```

Client presence is informational only.

---

# 49. HEALTH CHECK SYSTEM

Create a professional layered health model.

## Server

Check:

```text
Site Service
Database
Schema
Disk
Media Service
MediaMTX
Recognition Worker
HVX Host
Cameras
Gates
Printers
Payment provider where relevant
Backup state
```

## Client

Check:

```text
LAN
DNS/hostname
Server API
Authentication
Version compatibility
WebRTC/media
Latency
```

Use:

```text
HEALTHY
DEGRADED
OFFLINE
```

Do not mark the whole server offline because one camera is unavailable.

---

# 50. DATABASE HEALTH

Server should detect:

```text
DB unavailable
high latency
pool exhaustion
migration required
disk full
SQLite lock problems
PostgreSQL connection failure
```

Surface meaningful errors.

Example:

```text
Database unavailable.
Parking service is retrying.
```

rather than:

```text
sqlalchemy.exc.OperationalError...
```

Technical detail belongs in logs/diagnostics.

---

# 51. STORAGE HEALTH

Because evidence and logs can grow, monitor:

```text
disk free
media directory
database size
log directory
backup directory
```

Warn before disk exhaustion.

Do not allow CCTV/evidence retention to silently fill the system drive.

Use existing retention settings.

---

# 52. BACKUP SYSTEM

Server setup must configure backups.

At minimum support:

```text
manual backup
scheduled local backup
retention
backup verification
```

For PostgreSQL use a valid PostgreSQL backup mechanism.

For SQLite use safe SQLite backup semantics.

Do not simply copy a live database file if that is unsafe.

Back up relevant configuration separately from secrets where appropriate.

---

# 53. RESTORE

Create a controlled restore workflow.

Restore must:

```text
require administrator
warn clearly
stop write-producing services
backup current state first
restore
verify
restart
health-check
```

Never restore while recognition/session writes continue.

---

# 54. CONFIGURATION EXPORT

Provide an optional safe configuration export for deployment/recovery.

It may include:

```text
site topology
gate definitions
camera non-secret configuration
tariffs
application settings
```

Do not include secrets by default.

Never export plaintext:

```text
camera passwords
database password
payment secrets
admin passwords
```

---

# 55. LOGGING

Use per-component logs.

Examples:

```text
site-service.log
media-service.log
recognition-worker.log
hvx-host.log
desktop.log
setup.log
```

Setup operations must be logged.

Redact credentials.

Provide:

```text
Open Logs
Export Diagnostic Bundle
```

for administrators.

Diagnostic bundle must redact secrets.

---

# 56. WINDOWS FIREWALL

Server setup should detect/configure the required Windows firewall rules with administrator approval.

Only expose what clients require.

Potentially:

```text
SmartPark API
MediaMTX WebRTC signaling
MediaMTX ICE UDP/TCP
```

based on actual architecture.

Do NOT expose:

```text
MediaMTX control API 9997
MediaMTX metrics 9998
internal RTSP 8554
HVX SDK host 8765
PostgreSQL
```

to the LAN unless specifically required by architecture.

Current internal services using localhost should remain localhost where possible.

---

# 57. MEDIA CLIENT NETWORKING

Verify WebRTC from the second physical PC.

Test:

```text
Server camera
   ↓
MediaMTX
   ↓
LAN
   ↓
Client desktop
```

Check:

```text
WHEP URL
ICE candidates
UDP/TCP 8189
firewall
server hostname/IP
codec
reconnect
```

Do not declare client/server complete until remote live video actually works.

---

# 58. CLIENT VIDEO MUST NOT DUPLICATE RECOGNITION

Opening live view from Client 2 must not start another recognition worker.

Opening five clients must not create five FastALPR pipelines.

Architecture:

```text
ONE server recognition pipeline
             │
             ├── client A viewer
             ├── client B viewer
             └── client C viewer
```

---

# 59. OPERATOR ACTIONS

Remote client actions such as:

```text
manual gate open
receipt reprint
session correction
payment operation
subscriber management
camera configuration
```

must go through:

```text
Client
 ↓
authenticated API
 ↓
permission check
 ↓
audit
 ↓
server action
```

Never:

```text
Client → hardware directly
```

---

# 60. AUDIT LOG

Administrative/critical actions should record:

```text
who
what
when
which client
target
result
```

Especially:

```text
manual gate open
configuration change
camera change
tariff change
user change
database restore
deployment change
```

Do not log passwords/secrets.

---

# 61. SETUP SUMMARY

Before applying configuration show:

```text
SMARTPARK DEPLOYMENT

Role
    Site Server

Site
    <configured site>

Server
    <hostname / address>

Database
    PostgreSQL / SQLite

Cameras
    4 configured

Gates
    2 configured

Recognition
    FastALPR ready

Media
    MediaMTX ready

Administrator
    <username>

Firewall
    Ready

Backup
    Configured
```

Then:

```text
[Back] [Apply Configuration]
```

---

# 62. APPLY CONFIGURATION TRANSACTIONALLY

Do not write half the configuration after each wizard page.

Maintain draft configuration.

On Apply:

```text
validate
backup existing config
write temporary config
configure database
migrate if required
configure services
configure firewall
test
atomically activate config
mark CONFIGURED
```

If a critical step fails:

```text
rollback
```

and remain in setup.

---

# 63. SETUP COMPLETION

After successful server setup:

```text
✓ Database ready
✓ Site Service ready
✓ Media service ready
✓ Recognition ready
✓ Cameras reachable
✓ SmartPark configured
```

Then:

```text
[Start SmartPark]
```

For client:

```text
✓ Server found
✓ Site verified
✓ API compatible
✓ Media available
✓ SmartPark workstation configured
```

Then:

```text
[Open SmartPark]
```

---

# 64. NORMAL STARTUP AFTER CONFIGURATION

Do NOT show wizard again.

### Server desktop

```text
SmartPark.exe
 ↓
read config
 ↓
check local server services
 ↓
login
```

### Client

```text
SmartPark.exe
 ↓
read config
 ↓
connect server
 ↓
login
```

Keep startup fast.

Do not run full camera discovery/database migration every time the desktop opens.

---

# 65. RECONFIGURATION

Administrator should be able to explicitly launch:

```text
SmartPark Deployment Configuration
```

from:

```text
Settings → Deployment → Reconfigure
```

or a separate utility.

Dangerous changes must warn appropriately.

Examples:

```text
Server → Client
database migration
server address change
site identity change
```

Do not wipe data.

---

# 66. UNINSTALL

Professionalize uninstall behavior.

Ask whether to:

```text
Remove application only
```

or:

```text
Remove application and local SmartPark data
```

Default should preserve data.

Never silently delete:

```text
database
evidence
backups
configuration
logs
```

during normal uninstall/update.

---

# 67. UPDATE SAFETY

Prepare architecture for future updates.

Update should preserve:

```text
deployment configuration
database
evidence
camera credentials
site settings
users
backups
```

Server update should:

```text
backup
install
migrate
health-check
```

Client update should not affect server data.

---

# 68. SERVER FAILURE BEHAVIOR

If server fails, clients should show:

```text
SITE SERVER OFFLINE
```

not become alternative servers.

Do NOT implement automatic leader election/failover yet.

That is a separate high-availability project.

Avoid split-brain.

---

# 69. FUTURE BACKUP SERVER

Design configuration so a future architecture can support:

```text
Primary Server
Standby Server
```

but DO NOT implement automatic failover now.

A parking system controlling physical gates must not casually have two active authorities.

---

# 70. SERVER MACHINE SHOULD HAVE A STABLE IDENTITY

Use existing `node_id` mechanisms where appropriate.

Separate concepts:

```text
installation_id
server_id
node_id
site_id
```

only where each has a real purpose.

Do not create five redundant UUIDs.

Document semantics in code.

---

# 71. EXISTING NODE SCOPE

Current `node_scope.py` supports gate-specific recognition ownership.

Do not break it.

But ordinary workstation clients should never participate in recognition scope.

Conceptually:

```text
OPERATOR_CLIENT:
recognition_scope = NONE
```

---

# 72. SERVER DATABASE ACCESS BY SERVICES

Server-side processes such as:

```text
Site Service
Media Service
Recognition Worker
```

may legitimately access the authoritative server DB according to current architecture.

Operator clients may not.

Do not unnecessarily force every internal server service through HTTP if current direct DB access is reliable.

---

# 73. CLIENT-SAFE MEDIA ENDPOINT API

Server API should return client-usable media information without exposing camera credentials.

Client may receive:

```text
camera ID
camera name
gate
direction
WHEP endpoint
health
```

It must NOT receive:

```text
rtsp://admin:password@camera...
```

unless an explicit privileged diagnostic operation requires it.

---

# 74. SERVER URL ABSTRACTION

Do not use hardcoded:

```text
localhost
127.0.0.1
192.168.x.x
```

throughout UI code.

Create one deployment-aware endpoint resolver.

Examples:

```text
API internal URL
API client URL
Media internal URL
Media client URL
```

Centralize them.

---

# 75. TIME SYNCHRONIZATION

Multi-PC parking systems depend on time.

During setup/health checks inspect Windows clock/timezone.

Server is authoritative for business timestamps.

Clients display server timestamps appropriately.

Warn if client/server clock difference is excessive.

Do not let client local time determine parking duration/payment authority.

---

# 76. MACHINE NAMES

Allow a friendly workstation name:

```text
Control Room
Gate A Office
Manager Office
```

in addition to Windows hostname.

This helps diagnostics and connected-client display.

---

# 77. CLIENT DISPLAY SETTINGS REMAIN LOCAL

Existing local settings such as:

```text
appearance
text size
window geometry
```

should remain client-local.

Do not unnecessarily synchronize UI preferences through the site database.

---

# 78. SERVER SETTINGS ARE CENTRAL

Settings affecting parking behavior must remain server-side:

```text
tariffs
grace periods
gate rules
camera configuration
recognition settings
payment settings
site timezone
```

Clients only edit them through authorized API calls.

---

# 79. TEST MATRIX

Implement automated tests where possible.

Then perform physical LAN tests.

## First-run

Test:

```text
fresh server
fresh client
cancel wizard
resume wizard
invalid config
successful config
```

## Server

Test:

```text
SQLite existing installation
PostgreSQL if available
database unavailable
schema old
migration
service restart
Windows restart
camera unavailable
MediaMTX unavailable
```

## Client

Test:

```text
correct server
wrong IP
server offline
server becomes online
server disconnects while logged in
server returns
wrong SmartPark server identity
version mismatch
login failure
```

## Multiple clients

Test:

```text
Client A
Client B
Client C
```

simultaneously.

Ensure they do not create additional recognition/camera sessions.

## Media

Test live view from another physical PC.

## Permissions

Test:

```text
Admin
Operator
Kiosk Operator
```

according to existing permissions.

## Hardware

Verify remote manual gate command:

```text
Client
→ Server API
→ authorization
→ audit
→ physical gate
```

with explicit controlled testing.

---

# 80. EXISTING INSTALLATION MIGRATION

This is extremely important because SmartPark is already running against real cameras.

The new version must recognize the existing installation.

Do NOT force a destructive fresh setup.

When an existing installation has:

```text
database
cameras
gates
users
configuration
```

provide:

```text
Existing SmartPark installation detected.
```

Offer:

```text
Upgrade this computer to Site Server
```

and import/preserve the existing configuration.

Before conversion:

```text
backup
validate
```

After conversion:

```text
compare camera count
compare gate count
compare users
compare active configuration
```

Do not make the user manually re-enter all four cameras unless necessary.

---

# 81. PRESERVE CURRENT WORKING CAMERA SYSTEM

The currently working real-camera behavior is the baseline.

Do not rewrite:

```text
HVX camera adapter
gate control
FastALPR
recognition runtime
MediaMTX pipeline
entry/exit logic
```

just to implement deployment configuration.

Changes to those components must be minimal and directly required for remote clients/server ownership.

---

# 82. IMPORTANT FAILURE BOUNDARY

Configuration work must not reintroduce the previous camera problems:

```text
video freezes
recognition stalls
duplicate sessions
duplicate gate actions
```

After implementation, repeat the current real-camera soak test.

At minimum verify:

```text
server alone
server + one client
server + multiple live views
```

Compare CPU/memory/video behavior.

---

# 83. CLIENT LOAD SHOULD BE CHEAP

Adding a workstation should mainly add:

```text
API requests
WebRTC viewer
```

not:

```text
another FastALPR model
another detector
another OCR model
another camera SDK session
another upstream RTSP session
```

Measure this.

---

# 84. SERVER DASHBOARD

The Site Server should provide an administrator overview:

```text
SMARTPARK SITE

Server             Online
Database           Healthy
Media              Healthy
Recognition        Healthy
HVX Host           Healthy

Cameras            4 / 4
Gates              2 / 2
Clients            2 online

Disk                68% free
Last backup         Today 02:00
Uptime              3d 14h
```

Do not overload the normal operator screen with infrastructure telemetry.

---

# 85. PROFESSIONAL ERROR MESSAGES

Translate technical failures.

Instead of:

```text
ConnectError [WinError 10061]
```

show:

```text
SmartPark Site Server could not be reached.
```

Details:

```text
Connection to 192.168.x.x:8760 was refused.
```

Keep raw details in diagnostics/logs.

---

# 86. DIAGNOSTICS TOOL

Create a useful deployment diagnostics operation.

For client:

```text
Network adapter
Server DNS
Ping/TCP
API
Authentication
Version
WebRTC signaling
ICE/media
Latency
```

For server:

```text
Database
Services
Ports
MediaMTX
Recognition
HVX
Cameras
Gate hardware
Disk
```

Allow exporting a redacted diagnostic report.

---

# 87. DO NOT OVERENGINEER DISTRIBUTED SYSTEMS

This is currently a LAN parking installation.

Do NOT introduce:

```text
Kubernetes
Kafka
RabbitMQ
service mesh
distributed consensus
microservice explosion
```

Use the current architecture.

We need a reliable Site Server and thin operator workstations.

---

# 88. CONFIGURATION STORAGE DESIGN

Do not put everything in `.env`.

Separate:

### Installation/deployment configuration

Local machine:

```text
role
server endpoint
installation identity
service ownership
```

### Site configuration

Authoritative database:

```text
site
gates
cameras
tariffs
recognition settings
```

### Secrets

Secure secret storage:

```text
camera passwords
provider credentials
database password
```

### UI preferences

Local workstation:

```text
theme
text size
window geometry
```

This separation is important.

---

# 89. CONFIGURATION VERSIONING

Persist a configuration schema version.

Example concept:

```text
config_version = 1
```

Future versions can migrate local deployment configuration safely.

Do not make future upgrades depend on guessing which fields exist.

---

# 90. ATOMIC LOCAL CONFIGURATION

When saving deployment configuration:

```text
write temporary file
fsync where practical
validate
atomic replace
```

Avoid corrupted configuration if Windows loses power during setup.

---

# 91. SECRET FILE PERMISSIONS

Restrict local sensitive files appropriately on Windows.

Do not rely solely on "hidden" files for security.

Use DPAPI where current architecture supports it.

---

# 92. STARTUP PERFORMANCE

Client startup should not wait for:

```text
camera discovery
FastALPR initialization
MediaMTX startup
HVX initialization
database migration
```

because those belong to server.

Client should be able to reach login quickly when server is healthy.

---

# 93. FINAL INSTALLER EXPERIENCE

The long-term user experience should approximately be:

```text
Run SmartPark Setup.exe
       ↓
Install files
       ↓
Launch SmartPark Configuration
       ↓
Choose:
  Site Server
  Operator Workstation
       ↓
Configure
       ↓
Finish
```

Afterward Start Menu should contain appropriate entries such as:

```text
SmartPark
SmartPark Deployment Configuration
SmartPark Diagnostics
```

Do not expose developer `.bat` files to ordinary operators as the primary experience.

Existing scripts may remain underneath.

---

# 94. DESKTOP BRANDING

Use consistent:

```text
SmartPark
```

branding.

Avoid exposing implementation terms such as:

```text
FastAPI
SQLAlchemy
MediaMTX
FFmpeg
NetSDK
WHEP
```

to ordinary operators unless they open technical diagnostics.

Technicians can see those details.

---

# 95. DO NOT REMOVE DEVELOPMENT MODE

Developers still need:

```text
python development startup
localhost
SQLite
testing
Camera Lab
```

Preserve a developer workflow.

Production packaging and development workflow should coexist.

---

# 96. IMPLEMENT IN PHASES

Do NOT attempt one giant rewrite.

### Phase 1 — Architecture audit

Map current:

```text
startup
services
database
media
recognition
desktop
packaging
```

### Phase 2 — Deployment configuration model

Implement:

```text
SITE_SERVER
OPERATOR_CLIENT
optional EDGE_NODE
```

and configuration persistence.

### Phase 3 — Deployment-aware launcher

Stop clients from starting server processes.

### Phase 4 — Configurable API endpoint

Remove desktop localhost assumption.

### Phase 5 — Remote media

Make server WHEP/WebRTC work correctly from client PC.

### Phase 6 — Setup wizard

Implement first-run UI/state machine.

### Phase 7 — Server preflight/database configuration

Implement validation/migration/backup.

### Phase 8 — Client pairing

Implement discovery/manual connection/identity validation.

### Phase 9 — Windows services/firewall

Professionalize server installation.

### Phase 10 — Diagnostics/health

Implement deployment-aware health.

### Phase 11 — Existing installation upgrade

Preserve current working deployment.

### Phase 12 — Physical two-PC acceptance test

Actually test:

```text
PC 1 server
PC 2 workstation
```

### Phase 13 — Soak test

Run server + client against real cameras.

Commit in small reviewable groups.

---

# 97. PHYSICAL ACCEPTANCE TEST

This task is NOT complete merely because unit tests pass.

On the actual LAN verify:

```text
SERVER PC
    4 real cameras
    recognition running
    parking running
    MediaMTX running

CLIENT PC
    SmartPark workstation
```

Then verify:

### Client

```text
login works
dashboard loads
sessions load
camera live view works
recognition results appear
permissions work
```

### Server

```text
recognition remains stable
video remains stable
CPU remains acceptable
memory remains bounded
```

### Remote operations

Safely verify:

```text
authorized gate command
session operation
receipt operation if available
```

### Failure

Disconnect LAN cable from client.

Server parking must continue.

Reconnect client.

Client must recover.

Close client.

Server must continue.

Restart server desktop UI.

Server services must continue.

Restart Windows server.

Services must recover automatically.

---

# 98. FINAL REPORT REQUIRED

When complete, report:

## Architecture before

Show current topology.

## Architecture after

Show final:

```text
Server
Clients
database
media
recognition
hardware
```

## Existing installation handling

Explain how the current real installation was preserved.

## Configuration storage

List:

```text
what is local
what is server DB
what is secret
what is client-local
```

## Database

Report:

```text
engine
schema
migration status
backup
```

## Networking

Report:

```text
API binding
client URL
WebRTC ports
firewall rules
internal-only ports
```

## Services

Report all Windows services and startup/recovery configuration.

## Security

Report:

```text
authentication
secret storage
firewall
database isolation
```

## Tests

Report automated and physical tests separately.

Never claim a physical test passed unless actually performed.

## Performance

Compare:

```text
server alone
server + client
```

including:

```text
CPU
memory
live video
recognition latency
```

## Changed files

List all changed files and purpose.

## Rollback

Explain exactly how to return the existing server to the previous working version/configuration.

---

# 99. NON-NEGOTIABLE INVARIANTS

After this work:

### 1.

An OPERATOR_CLIENT must never automatically become a server.

### 2.

An OPERATOR_CLIENT must never directly access the production database.

### 3.

An OPERATOR_CLIENT must never run FastALPR.

### 4.

An OPERATOR_CLIENT must never connect directly to gate hardware.

### 5.

Closing all clients must not stop parking.

### 6.

Server desktop UI crashing must not stop parking.

### 7.

A client losing network connectivity must not affect server parking.

### 8.

Multiple clients must not multiply recognition pipelines.

### 9.

Existing camera/gate configuration must survive upgrade.

### 10.

Existing parking data must survive upgrade.

### 11.

Database migration must have backup + rollback.

### 12.

Setup wizard must not run on every normal startup.

### 13.

Normal operators must not need `.env`, PowerShell, Python or database knowledge.

### 14.

One failed camera must not make the entire server unhealthy.

### 15.

One failed client must have zero effect on physical gate automation.

---

# 100. FINAL PRODUCT EXPERIENCE

The goal is that a technician can take a clean Windows PC and install SmartPark without editing source code.

## Server

```text
Install SmartPark
      ↓
Choose Site Server
      ↓
System check
      ↓
Configure network
      ↓
Configure database
      ↓
Create administrator
      ↓
Configure site
      ↓
Configure gates
      ↓
Discover/add cameras
      ↓
Test hardware
      ↓
Configure backup
      ↓
Review
      ↓
Apply
      ↓
SmartPark operational
```

## Additional workstation

```text
Install SmartPark
      ↓
Choose Operator Workstation
      ↓
Find/enter Site Server
      ↓
Test connection
      ↓
Verify site/server identity
      ↓
Finish
      ↓
Login
      ↓
Same authoritative SmartPark site
```

From then onward:

```text
Double-click SmartPark
        ↓
Login
        ↓
Work
```

No setup wizard.

No command line.

No `.env` editing.

No database configuration on client PCs.

No camera configuration duplication.

No second recognition engine.

No second parking authority.

Build SmartPark as if this were a commercial parking/access-control product that must be installed, maintained and recovered by another competent technician without needing the original developer standing beside them.

Most importantly:

**preserve the currently working real-camera parking pipeline while placing a professional deployment/configuration layer around it.**
