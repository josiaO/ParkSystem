# Camera ownership and multi-computer deployment

This document describes the topology currently implemented by Zirp. The
separate `SMARTPARK_FLEXIBLE_NODES_EDGE_CACHE_OFFLINE_ARCHITECTURE.md` file is
a future architecture proposal, not an instruction to enable an unimplemented
edge cache or offline synchronization layer.

The current release fails closed at the media boundary: a process can stream
and recognize only cameras in its assigned gate scope. The central Site Server
may list and configure the complete camera registry so an administrator can
add a camera or repair a gate assignment; live camera pickers still hide
foreign-node producers. Live endpoint, WHEP, MJPEG,
snapshot, preview, stream telemetry, probe and viewer-state requests for a
different node's camera return HTTP 403 and write a node-scope warning to the
Site Service log. This prevents a stale UI camera ID from opening another
node's local MediaMTX/SDK producer.

SmartPark calls each physical entry/exit pair a **gate**. Thus your two lanes
with four cameras are two gates: one processing PC handles each gate. Each
processing PC runs its local camera host, MediaMTX, recognition worker, Site
Service and desktop. Video stays at its lane; a node never decodes another
node's cameras. A Processing Node is different from an Operator Workstation:
the workstation is UI-only, while the processing node owns one dynamically
assigned gate.

## Single lane

Use the normal installation and local SQLite database. The default role is
`SERVER`. Assign its entry and exit cameras to the same gate. Pin
`SMARTPARK_RECOGNITION_GATE_ID` to that gate ID, or choose it in Live Gates.
No second computer or PostgreSQL installation is needed.

In the browser, select the gate under Live Gates and use **Assign this PC to
selected gate**. The Site Server can configure all camera records, but a
production process cannot stream or recognize an unassigned or foreign-gate
camera until ownership is assigned. This keeps the management registry global
without allowing one node to open another node's local producer.

## Two or more lanes

For multiple computers that each process cameras, provision PostgreSQL on the
server, create the parking database and user, and allow authenticated
connections from the lane PCs on the private site network. Each processing
computer must have a unique installation/node identity and its own persisted
gate assignment (or an explicit `SMARTPARK_RECOGNITION_GATE_ID`). The
Processing Node wizard must be pointed at the Site Server API and the Site
Server's PostgreSQL host/database. The node runs local camera, MediaMTX and
recognition services, but it does not create a second site database or run
schema migrations. Each local service registers and consumes only its own
camera paths. Do not put a SQLite database on a network share. Existing SQLite
transactions are **not** migrated automatically by changing the URL.

### Processing Node credentials and control boundary

The Site Server pairing endpoint returns installation/site identity only. It
does not send the Site Server administrator password, PostgreSQL password,
camera passwords, RTSP URLs with credentials, or secret-store references.
During Processing Node setup, enter a dedicated PostgreSQL login approved for
the node deployment; never reuse the Site Server web administrator password or
the PostgreSQL `postgres` superuser password. The node stores its database
secret locally in its protected secret store.

During Processing Node setup, create the node's own username and password in
the wizard. Zirp creates that account in the shared site database with only the
built-in **Processing Node** role. The node login rejects the Site Administrator
account and every other shared-database username. The node password is not
written to `deployment.json`; only its Argon2 password hash is stored.

Do not use the Site Administrator account on a node. The Processing Node role is
deliberately limited to camera/media, assigned-gate control and hardware
diagnostics.

The Processing Node wizard does not create or request a local Site Server
administrator password. After the database test passes, setup completes and the
normal sign-in dialog opens with the node username. If the entered node password
is shorter than 12 characters, setup rejects it and identifies the password
policy. The node cannot use the Site Administrator password as a substitute.

The node API is fail-closed even when an administrator session from the shared
database is used on the node. It exposes only assigned-camera camera/media
operations, gate names/assigned-gate control, and local hardware diagnostics.
Users, roles, site settings, tariffs, payments, subscribers, backups, and
central topology return HTTP 403 on a Processing Node. A node's diagnostics
bundle is also filtered to its own gate and contains no credential reference.
Use the Site Server for those operations.

SQLite remains supported for a single-computer server or evaluation. A
two-laptop test where the server owns SQLite and the second laptop is expected
to process its own gate is not a supported synchronized edge deployment in
this release: SQLite cannot safely be the shared multi-process database, and
the future edge read-cache/journal/sync design has intentionally not been
implemented here. Use the second laptop as an Operator Workstation, or move
the multi-computer processing deployment to PostgreSQL before field use.

If the site deliberately wants central evidence, create a shared evidence
directory on the server, accessible with read/write permissions to the
accounts running SmartPark on both processing PCs. Use the same UNC path on
both computers. This is an evidence store, not a camera/video transport: a
node must never point its MediaMTX or live-stream path at another node. Local
SDK credentials remain in each PC's secret store; configure each camera's
password from the PC assigned to that camera.

Place these values in `.env` in each installed SmartPark directory. Replace
database credentials, host, share and gate IDs with the site's actual values.
Existing environment variables take precedence over `.env`.

Server PC:

```dotenv
SMARTPARK_NODE_ROLE=SERVER
SMARTPARK_NODE_ID=lane-1-server
SMARTPARK_RECOGNITION_GATE_ID=1
SMARTPARK_DATABASE_URL=postgresql+psycopg://parking:CHANGE_ME@SERVER_IP/parking
SMARTPARK_SHARED_MEDIA_DIR='\\SERVER_NAME\SmartParkMedia'
```

Second processing PC (Processing Node installer):

```dotenv
SMARTPARK_NODE_ROLE=SERVER
SMARTPARK_NODE_ID=lane-2-client
SMARTPARK_RECOGNITION_GATE_ID=2
SMARTPARK_DATABASE_URL=postgresql+psycopg://parking:CHANGE_ME@SERVER_IP/parking
SMARTPARK_SHARED_MEDIA_DIR='\\SERVER_NAME\SmartParkMedia'
```

Start the server first to initialize the schema and site. On the second PC,
run `Install-SmartPark-Node.bat` (or choose `N` in `Install-SmartPark.bat`).
That installer locks the wizard to Processing Node, asks for the existing Site
Server address, hides SQLite, and checks the same PostgreSQL database without
migrating it. The node starts with no ownership and therefore opens no camera.
After login, assign its gate in Live Gates. Its installation/node identity
must not be copied from the server. Each node's assignment is stored
separately; an environment-pinned assignment cannot be changed by another
lane's UI. MediaMTX, software
recognition, ONVIF polling and automatic SDK connections use the assigned pair.
Only the server runs background external-payment reconciliation. If the
second PC was configured as an Operator Workstation, it is intentionally a UI
client and the server—not that workstation—will save captures and media. Do
not use the Operator Workstation installer when the PC must own cameras.

This is a connected deployment: shared parking decisions require the server
database and network. It does not provide autonomous offline parking or database
replication. Provisioning PostgreSQL, migrating an existing SQLite database and
testing concurrent cross-lane parking on the real network are deployment steps,
not actions performed by this source update.

## Playback and acceptance

Rebuild/install the Windows kit. The desktop uses Qt Essentials; PostgreSQL
deployments also require the bundled Psycopg driver. Do not copy a Linux virtual
environment into Windows.

The installer registers the Recognition Worker as a background task and activates
MediaMTX and the new recognition pipeline even for upgraded sites with legacy
rollout settings. The desktop also starts the media and recognition owners if
scheduled startup was missed; instance locks prevent duplicate owners. They wait
for the Site Service to initialize the database. MediaMTX startup errors are retained in
`%ProgramData%\SmartParkEdge\logs\mediamtx.log`.

SDK cameras use the shared SDK JPEG producer without speculative RTSP pulls.
Generic RTSP cameras use MediaMTX. Desktop reads the latest JPEG from the local
gateway; browser WebRTC uses the existing WHEP transport with MJPEG fallback.
For browser clients, permit TCP 8889 and UDP/TCP 8189 on the private LAN using
`Enable-MediaMTX.ps1 -LiveView`. Configure camera H.264 output for broad browser
compatibility. SDK plate events and control remain independent of video.

Verify on each PC: only its two cameras are connected, both videos move, each
vehicle produces a full-car snapshot and crop, and camera reconnects recover.
Measure arrival-to-plate latency after model warmup using real vehicles. Test
entry on gate 1 and exit on gate 2 against the shared database before rollout.
Automated tests and generated-video playback cannot establish field latency.
Camera Lab reports native MediaMTX byte flow separately from decoded frames.
Advancing bytes alone produce a DEGRADED result requiring a player check, not
a false claim that decoded FPS or display latency passed.
