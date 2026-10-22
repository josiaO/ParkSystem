# One PC per entry/exit pair

SmartPark calls each physical entry/exit pair a **gate**. Thus your two lanes
with four cameras are two gates: server PC handles gate 1, client PC handles
gate 2. Each PC runs its local camera host, MediaMTX, recognition worker, Site
Service and desktop. Video stays at its lane; the server does not decode four
cameras. The client is an edge processor, not just a remote desktop viewer.

## Single lane

Use the normal installation and local SQLite database. The default role is
`SERVER`. Assign its entry and exit cameras to the same gate. Pin
`SMARTPARK_RECOGNITION_GATE_ID` to that gate ID, or choose it in Live Gates.
No second computer or PostgreSQL installation is needed.

## Two or more lanes

Provision PostgreSQL on the server, create the parking database and user, and
allow authenticated connections from the lane PCs on the private site network.
Both PCs use the same PostgreSQL database, so an entry from one lane is visible
at the other. Do not put a SQLite database on a network share. Existing SQLite
transactions are **not** migrated automatically by changing the URL.

Create a shared evidence directory on the server, accessible with read/write
permissions to the accounts running SmartPark on both PCs. Use the same UNC
path on both computers. Local SDK credentials remain in each PC's secret store:
configure each camera's password from the PC assigned to that camera.

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

Client PC:

```dotenv
SMARTPARK_NODE_ROLE=CLIENT
SMARTPARK_NODE_ID=lane-2-client
SMARTPARK_RECOGNITION_GATE_ID=2
SMARTPARK_DATABASE_URL=postgresql+psycopg://parking:CHANGE_ME@SERVER_IP/parking
SMARTPARK_SHARED_MEDIA_DIR='\\SERVER_NAME\SmartParkMedia'
```

Start the server first to initialize the schema and site. Then start the client.
Client configuration fails early if its shared database, lane ID or evidence
directory setting is missing. Each node's UI assignment is stored separately;
an environment-pinned assignment cannot be changed by another lane's UI.
MediaMTX, software recognition, ONVIF polling and automatic SDK connections use
the assigned pair. Viewing another camera does not change recognition ownership.
Only the server runs background external-payment reconciliation.

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
