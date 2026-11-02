# SMARTPARK PLATFORM ARCHITECTURE — SEPARATE SITE SERVER, EDGE RUNTIME, OPERATOR APP AND DRIVER PORTAL

## Mission

I want you to inspect the CURRENT Zirp system and evolve its architecture so the system is understandable as a professional parking platform rather than one large application where cameras, parking logic, administration, payment, Internet access and hardware are mixed together.

**Do not immediately start moving files or rewriting code.**

First audit what already exists, map each existing component to the architecture defined below, identify what is already correct, and produce an implementation plan.

The target conceptual architecture is:

```text
                         SMARTPARK PLATFORM

 ┌───────────────────────────────────────────────────────────────┐
 │                     PRIVATE PARKING SITE                      │
 │                                                               │
 │                  ┌─────────────────────┐                      │
 │                  │  1. SITE SERVER     │                      │
 │                  │                     │                      │
 │                  │ Parking authority   │                      │
 │                  │ Sessions            │                      │
 │                  │ Tariffs             │                      │
 │                  │ Payments            │                      │
 │                  │ Users/RBAC          │                      │
 │                  │ Node registry       │                      │
 │                  │ PostgreSQL          │                      │
 │                  └──────────┬──────────┘                      │
 │                             │                                 │
 │                 Private LAN / authenticated API               │
 │                             │                                 │
 │          ┌──────────────────┼──────────────────┐              │
 │          │                                     │              │
 │ ┌────────▼────────┐                   ┌────────▼────────┐     │
 │ │ 2. EDGE NODE A  │                   │ 2. EDGE NODE B  │     │
 │ │                 │                   │                 │     │
 │ │ Cameras         │                   │ Cameras         │     │
 │ │ ALPR            │                   │ ALPR            │     │
 │ │ Booms           │                   │ Booms           │     │
 │ │ Printer         │                   │ Printer         │     │
 │ │ QR scanner      │                   │ QR scanner      │     │
 │ │ Local cache     │                   │ Local cache     │     │
 │ └─────────────────┘                   └─────────────────┘     │
 │                                                               │
 │                    ┌──────────────────┐                       │
 │                    │ 3. OPERATOR APP  │                       │
 │                    │                  │                       │
 │                    │ Staff/Admin      │                       │
 │                    │ Monitoring       │                       │
 │                    │ Search           │                       │
 │                    │ Manual actions   │                       │
 │                    │ Reports          │                       │
 │                    └──────────────────┘                       │
 └───────────────────────────────────────────────────────────────┘

                              │
                    CONTROLLED SECURITY BOUNDARY
                              │
                              ▼

                         PUBLIC INTERNET

                    ┌──────────────────────┐
                    │ 4. DRIVER PORTAL     │
                    │                      │
                    │ QR landing page      │
                    │ Vehicle information  │
                    │ Vehicle image        │
                    │ Parking duration     │
                    │ Amount due           │
                    │ Mobile payment       │
                    │ Payment status       │
                    └──────────────────────┘
```

This architecture is the target mental model.

Do NOT interpret this diagram as permission to rewrite currently working systems.

---

# PART 1 — THE FOUR SMARTPARK SURFACES

SmartPark should be understandable as four cooperating surfaces.

# 1. SMARTPARK SITE SERVER — THE BRAIN

The Site Server owns authoritative business state.

It is responsible for:

- authoritative PostgreSQL database;
- parking sessions;
- entry/exit state;
- tariff calculation;
- payment ledger;
- registered vehicles;
- subscriptions/access plans;
- users;
- roles and permissions;
- site configuration;
- gates/lanes;
- node registry;
- node assignments;
- audit history;
- reporting data;
- payment reconciliation;
- synchronization authority.

The Site Server answers:

```text
Who entered?
When did they enter?
Which gate?
Is the parking session active?
How much is currently owed?
Has the driver paid?
Is this vehicle subscribed?
Which node owns this gate?
May this vehicle exit?
```

It is the authoritative source of truth.

---

# 2. SMARTPARK EDGE/GATE RUNTIME — THE EYES AND HANDS

An Edge Node interacts with physical equipment.

Examples:

```text
Gate A computer
Gate B computer
Gate C computer
```

It is responsible for its assigned local resources:

```text
camera
       ↓
streaming
       ↓
ALPR
       ↓
plate event

printer
QR scanner
boom controller
presence/passage sensor
```

The Edge Node should NOT become another central Site Server.

Conceptually:

```text
SITE SERVER
"What should happen?"

EDGE NODE
"Interact with the physical world."
```

Example:

```text
Gate B Camera
     ↓
Gate B recognition
     ↓
T123ABC
     ↓
Site Server
     ↓
AUTHORIZED TO EXIT
     ↓
Gate B Node
     ↓
Gate B boom
```

For offline resilience the node may eventually contain:

```text
local cache
durable outbox/event journal
sync checkpoint
processed-command IDs
```

But this is not another authoritative parking database.

---

# 3. SMARTPARK OPERATOR APP — THE HUMAN CONTROL SURFACE

The Operator App is what:

```text
security personnel
cashier
parking operator
administrator
technician
manager
```

use.

It communicates primarily with the Site Server.

It should provide appropriate interfaces according to permission:

```text
Live Gates
Active Sessions
Search Vehicle
Payments
Exceptions
Registered Vehicles
Subscribers
Manual Gate Actions
Node Status
Camera Status
Reports
Administration
```

A human logged into a Gate B PC remains a human user.

Do not confuse:

```text
HumanPrincipal
```

with:

```text
NodePrincipal
```

The physical computer's node role must not determine the human's application permissions.

---

# 4. SMARTPARK DRIVER PORTAL — THE PUBLIC SURFACE

This is the ONLY SmartPark component intended to be publicly reachable from the Internet.

A driver scans the QR printed at entry using a normal phone camera.

Example:

```text
Receipt QR

https://pay.smartpark.example/p/<secure-token>
```

The driver sees:

```text
SMARTPARK

[vehicle entry image]

T 123 ABC

Entered
Gate A
31 Oct 2026 • 10:42

Parking duration
1h 17m

Parking fee
TZS 2,000

Paid
TZS 0

AMOUNT DUE
TZS 2,000

[ PAY TZS 2,000 ]

M-Pesa
Airtel Money
Mixx by Yas
etc.
```

After verified payment:

```text
✓ PAYMENT RECEIVED

Vehicle
T 123 ABC

TZS 2,000 PAID

You may proceed to an exit gate.
```

This interface must be mobile-first.

---

# PART 2 — VERY IMPORTANT INTERNET BOUNDARY

I do NOT want SmartPark to simply expose the entire Site Server to the Internet.

Do NOT expose:

```text
PostgreSQL
camera APIs
MediaMTX
WebRTC administration
gate-control endpoints
node APIs
operator APIs
admin endpoints
HVX SDK
printer services
recognition services
Windows gate computers
```

to the public Internet.

Conceptually:

```text
PRIVATE NETWORK                         INTERNET

Cameras ─┐
ALPR ────┤
Booms ───┤
Nodes ───┤
         │
     Site Server
         │
     PostgreSQL
         │
         │ controlled interface
         ▼
   ┌───────────────┐
   │ PUBLIC PAYMENT│
   │ BOUNDARY      │
   └───────┬───────┘
           │
           ▼
      Driver Portal
```

Audit the current `/p/{token}`, public session endpoints, payment-intent endpoints and provider webhook endpoints.

Determine what can safely become the Driver Portal rather than creating another application unnecessarily.

---

# PART 3 — DO NOT BUILD TWO PAYMENT SYSTEMS

Kiosk and phone payment must share the SAME business logic.

Do not implement:

```text
Kiosk payment system
+
separate mobile payment system
```

Instead:

```text
                  PARKING SESSION
                         │
                         ▼
                PAYMENT APPLICATION
                         │
               ┌─────────┴─────────┐
               │                   │
            KIOSK               PHONE
               │                   │
               └─────────┬─────────┘
                         ▼
                  PAYMENT LEDGER
                         │
                         ▼
                 SESSION PAID STATE
```

There should be one authoritative function/service for determining:

```text
session
vehicle
entry image
entry time
duration
current fee
amount paid
amount remaining
payment status
```

Both kiosk and Driver Portal consume this.

---

# PART 4 — SHARED SESSION PRESENTATION MODEL

Create/reuse a clean application service that produces a presentation model such as:

```json
{
  "session_reference": "P-20261031-00425",
  "plate": "T123ABC",
  "entry_gate": "Gate A",
  "entry_time": "...",
  "duration_seconds": 4620,
  "vehicle_image_url": "...",
  "plate_crop_url": "...",
  "currency": "TZS",
  "amount_due": 2000,
  "amount_paid": 0,
  "amount_remaining": 2000,
  "payment_status": "UNPAID",
  "can_exit": false
}
```

Do not necessarily use these exact field names.

Inspect current models/services first.

The point is:

```text
             SESSION PRESENTATION
                     │
           ┌─────────┴─────────┐
           │                   │
        KIOSK UI          DRIVER PORTAL
```

The two interfaces should display the same authoritative information.

---

# PART 5 — VEHICLE IMAGE

When the driver scans the receipt QR on either kiosk or phone, they should be able to see the vehicle captured at entry.

Current repository appears to already have public-token image endpoints such as:

```text
/p/{token}/snapshot.jpg
/p/{token}/crop.jpg
```

VERIFY this from current source.

Reuse existing evidence storage.

Do NOT create another camera capture pipeline.

Do NOT modify recognition to implement this.

The image shown must belong to the resolved parking session.

Security requirements:

- never expose arbitrary filesystem paths;
- never allow token manipulation to retrieve another session's image;
- use secure unguessable tokens;
- send appropriate cache/privacy headers;
- return a safe placeholder when evidence is unavailable.

---

# PART 6 — KIOSK EXPERIENCE

The kiosk should be optimized for:

```text
large display
touch interaction
fast scanning
simple payment
```

Example:

```text
┌────────────────────────────────────────┐
│               SMARTPARK                │
│                                        │
│          Scan Parking Receipt          │
│                                        │
│             [ QR ICON ]                │
└────────────────────────────────────────┘
```

After scan:

```text
┌────────────────────────────────────────┐
│               SMARTPARK                │
│                                        │
│      [ VEHICLE ENTRY IMAGE ]           │
│                                        │
│             T 123 ABC                  │
│                                        │
│ Entry: Gate A                          │
│ Time: 10:42                            │
│ Duration: 1h 17m                       │
│                                        │
│ Amount Due                             │
│ TZS 2,000                              │
│                                        │
│             [ PAY ]                    │
└────────────────────────────────────────┘
```

Do not duplicate fee calculations in kiosk frontend.

---

# PART 7 — MOBILE EXPERIENCE

The phone page should use the same design language but mobile layout.

Example:

```text
┌─────────────────────────┐
│       SMARTPARK         │
│                        │
│   [ VEHICLE IMAGE ]    │
│                        │
│       T 123 ABC        │
│                        │
│ Gate A                 │
│ 10:42                  │
│                        │
│ Parked      1h 17m     │
│ Due         TZS 2,000  │
│                        │
│ ─────────────────────  │
│                        │
│       TZS 2,000        │
│                        │
│     [ PAY NOW ]        │
│                        │
└─────────────────────────┘
```

Responsive, fast and usable on low-cost Android phones and mobile networks.

Do not load:

```text
camera streams
large JS bundles
operator UI
admin dependencies
```

on the public page.

---

# PART 8 — PAYMENT PROVIDER ARCHITECTURE

The Driver Portal may initiate payment.

But:

```text
browser says SUCCESS
```

must NEVER mean:

```text
ParkingSession = PAID
```

Correct:

```text
Driver Portal
     ↓
Payment Intent
     ↓
Mobile Money Provider
     ↓
Provider verification/webhook
     ↓
SmartPark Payment Service
     ↓
PaymentTransaction
     ↓
Authoritative session state
```

Preserve/reuse the current unified payment ledger if it already implements this correctly.

Do not rewrite it unnecessarily.

---

# PART 9 — INTERNET DEPLOYMENT: IMPLEMENT IN STAGES

I am still learning deployment architecture.

Therefore do NOT jump immediately to a complicated cloud microservice architecture.

Design this in two stages.

## Stage 1 — First real deployment

Allow the existing Site Server to host the narrow Driver Portal/payment endpoints.

Architecture:

```text
PHONE
  │
Internet
  │
HTTPS
  │
Reverse Proxy / Secure Tunnel
  │
  ├── ALLOW public Driver Portal/payment endpoints
  │
  └── BLOCK internal SmartPark APIs
          │
          ▼
     Site Server
          │
     PostgreSQL
```

PostgreSQL must remain private.

Port `5432` must never be publicly exposed.

Camera/MediaMTX/gate/node APIs remain private.

Document exactly which HTTP paths are public.

Use an explicit public route allowlist.

---

# PART 10 — FUTURE COMMERCIAL CLOUD ARCHITECTURE

Do NOT necessarily implement this now.

Document a future architecture for multiple SmartPark customer sites:

```text
                   SMARTPARK CLOUD
                pay.smartpark.co.tz
                        │
                Driver Portal
                Payment Gateway
                Webhooks
                        │
                  secure HTTPS
                        │
       ┌────────────────┼────────────────┐
       │                │                │
    Mall A           Mall B           Mall C
 Site Server       Site Server       Site Server
     │                  │                │
 Edge Nodes         Edge Nodes       Edge Nodes
```

The public cloud should eventually know only what it needs for public/payment operations.

It should not become a remote camera/gate-control backdoor.

---

# PART 11 — REPOSITORY ARCHITECTURE

Do not blindly reorganize the repository.

First map current code into:

```text
DOMAIN CORE
parking/session/tariff/payment/access decisions

SITE SERVER
central API/database/administration

EDGE RUNTIME
hardware/recognition/gate operation

OPERATOR
desktop/staff interface

DRIVER PORTAL
public session/payment interface
```

Then determine whether actual package restructuring is necessary.

Prefer logical boundaries before large physical file moves.

Possible future conceptual structure:

```text
smartpark/
│
├── domain/
├── site_server/
├── edge/
├── operator/
├── driver_portal/
└── shared/
```

But DO NOT move everything merely to make the repository look clean.

Current working imports, packaging and hardware code are more important.

---

# PART 12 — DEPLOYMENT BOUNDARIES

Create a deployment architecture proposal.

## Windows Edge Node

Likely contains:

```text
SmartPark Edge Runtime
MediaMTX
recognition worker
HVX SDK host
FastALPR
printer adapter
QR scanner adapter
gate controller
local cache/outbox
```

Do not Dockerize vendor hardware components merely for consistency.

## Site Server

Evaluate both current Windows deployment and future Linux deployment.

Future Linux Site Server may use:

```text
Dockerfile
Docker Compose
PostgreSQL
SmartPark API
reverse proxy
backup service
monitoring
```

Do NOT break the current Windows deployment to achieve this.

## Driver Portal

Initially may be served by Site Server.

Later may become separately deployable.

---

# PART 13 — PROTECTED SYSTEMS

THIS IS CRITICAL.

Do NOT rewrite or refactor the following merely to create these architectural boundaries:

### Streaming
Do not change:

```text
MediaMTX
WebRTC/WHEP
MJPEG
media gateway
frame buffers
FFmpeg parameters
SDK JPEG/live implementation
```

### Recognition
Do not change:

```text
FastALPR
detector
OCR
crop preprocessing
consensus
recognition scheduler
decoder
model loading
```

### Database engine
Do not change:

```text
SQLAlchemy engine creation
pooling
SessionLocal mechanics
Alembic engine
```

### Hardware
Do not rewrite:

```text
HVX/NetSDK
working camera connection
working boom commands
printer protocol
```

Solve architecture around their existing interfaces.

---

# PART 14 — SECURITY BOUNDARY

Produce an explicit endpoint classification.

Example:

| Surface | Public Internet | Site LAN | Localhost |
|---|---|---|---|
| Driver payment page | YES | YES | YES |
| Public session status | YES, token-scoped | YES | YES |
| Payment initiation | YES | YES | YES |
| Provider webhook | YES | — | — |
| Admin API | NO | YES | YES |
| Operator API | NO | YES | YES |
| Node sync | NO public Internet | YES | YES |
| Gate open | NO | controlled LAN | local |
| Camera admin | NO | controlled LAN | local |
| MediaMTX admin | NO | controlled LAN | local |
| PostgreSQL | NEVER | server/private only | YES |

Audit actual endpoints and produce the real table.

Do not trust route names alone.

Inspect authentication and authorization.

---

# PART 15 — PUBLIC TOKEN SECURITY

Receipt QR is effectively a temporary credential.

Audit:

```text
token entropy
token generation
token lookup
session exposure
image exposure
token reuse
closed-session behavior
rate limiting
enumeration resistance
logs
```

QR should not expose sequential database IDs.

A driver should only see information appropriate to their parking session.

---

# PART 16 — PRIVACY

The Driver Portal exposes:

```text
number plate
vehicle image
entry information
payment information
```

Treat this as sensitive operational information.

Do not expose:

```text
driver identity
other sessions
other vehicle history
internal camera addresses
filesystem paths
node information
staff information
```

Public responses should contain the minimum information required to identify and pay for the current visit.

---

# PART 17 — FAILURE BEHAVIOR

Design explicitly:

### Internet unavailable

Parking gates must continue operating locally.

Kiosk should continue according to site policy.

Phone payment temporarily unavailable.

Do NOT make gate operation depend on Internet.

### Mobile payment provider unavailable

Do not mark payment successful.

Offer kiosk/alternative payment.

### Site LAN unavailable

Edge Node follows configured degraded/offline policy.

### Driver Portal unavailable

Local parking operation continues.

This separation is one of the main reasons for this architecture.

---

# PART 18 — BRAND/PRODUCT LANGUAGE

Make the architecture visible in product terminology.

Use consistent terms:

```text
SmartPark Site Server
SmartPark Edge
SmartPark Operator
SmartPark Driver
```

Avoid confusing internal names such as:

```text
client A
client B
server client
processing client
server node client
```

Gate A/B are resource names, not software roles.

A computer can be:

```text
SmartPark Site Server + Edge
```

if it also operates a local gate.

---

# PART 19 — OBSERVABILITY

Site Server should eventually show:

```text
SITE
Rock City Mall

SERVER
● Online

EDGE NODES

Gate A Edge
● Online
2 Cameras
Recognition healthy
Printer healthy
QR Scanner healthy
Booms healthy

Gate B Edge
● Online
2 Cameras
Recognition healthy
Printer healthy
QR Scanner healthy
Booms healthy

PUBLIC PAYMENT
● Online
Provider connected
Last payment: ...
```

This should make the architecture understandable to technicians and operators.

Do not implement fake health indicators.

Use real telemetry.

---

# PART 20 — REQUIRED FIRST DELIVERABLE

Before making major changes, create:

```text
SMARTPARK_PLATFORM_ARCHITECTURE_AUDIT.md
```

It must contain:

1. current repository architecture;
2. mapping of every major existing component to:
   - Site Server;
   - Edge;
   - Operator;
   - Driver Portal;
   - shared/domain;
3. current entry workflow;
4. current exit workflow;
5. current kiosk workflow;
6. current mobile workflow;
7. current Internet-exposed endpoints;
8. current LAN-only endpoints;
9. current database ownership;
10. what is already implemented correctly;
11. what is mixed together incorrectly;
12. security boundary problems;
13. missing Driver Portal functionality;
14. missing kiosk functionality;
15. missing node/edge functionality;
16. recommended repository boundaries;
17. recommended deployment boundaries;
18. Stage-1 deployment;
19. future commercial/cloud deployment;
20. exact files that should change;
21. exact files that MUST NOT change;
22. P0/P1/P2 implementation plan.

Do NOT begin a large restructuring before this audit exists.

---

# PART 21 — IMPLEMENTATION ORDER

After the audit, implement incrementally.

## Phase 1
Establish logical Site Server / Edge / Operator / Driver boundaries without moving working subsystems.

## Phase 2
Create/reuse one authoritative session/payment presentation service shared by kiosk and Driver Portal.

## Phase 3
Polish Driver Portal:
- vehicle image;
- plate;
- gate;
- entry time;
- duration;
- current fee;
- payment status;
- mobile payment;
- paid confirmation.

## Phase 4
Polish kiosk using the same presentation/payment domain.

## Phase 5
Implement explicit public/private endpoint boundary.

## Phase 6
Add reverse-proxy/deployment configuration for narrow public access.

## Phase 7
Complete physical QR-scanner integration where missing.

## Phase 8
Complete node-local cache/outbox/synchronization separately.

## Phase 9
Create production deployment bundles.

## Phase 10
Perform complete field acceptance testing.

Run regression tests after every phase.

---

# PART 22 — DEFINITION OF DONE

The architecture should become understandable enough that a technician can say:

> The Site Server is the brain.
>
> SmartPark Edge controls the physical gate.
>
> SmartPark Operator is what staff use.
>
> SmartPark Driver is what customers see when they scan their receipt.
>
> Only SmartPark Driver needs public Internet access.
>
> Losing the Internet must not stop the parking gates.
>
> Losing the Site Server temporarily invokes Edge degraded-operation policy.
>
> PostgreSQL, cameras, recognition and gate controls are never exposed publicly.

And a developer should immediately know which subsystem owns a new feature.

---

# FINAL RULE

Do not turn this architectural clarification into another rewrite of the components that already work.

Especially:

**DO NOT TOUCH THE WORKING STREAMING PIPELINE.**

**DO NOT TOUCH THE WORKING RECOGNITION PIPELINE.**

**DO NOT TOUCH THE DATABASE ENGINE.**

**DO NOT REWRITE HVX/NETSDK OR THE WORKING GATE DRIVER.**

This task is primarily about defining **boundaries, ownership, interfaces, deployment surfaces and user experiences around the working SmartPark core**.

The final product should behave as one SmartPark platform while being internally divided into four understandable responsibilities:

```text
SITE SERVER = THINK

EDGE        = SENSE + ACT

OPERATOR    = MANAGE

DRIVER      = VIEW + PAY
```
