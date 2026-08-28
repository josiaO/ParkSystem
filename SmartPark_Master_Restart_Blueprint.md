# SmartPark Edge — Master Restart Blueprint

**Purpose:** New source of truth for Cursor. Preserve the now-working HVX camera/boom integration, but rebuild the product around clean, universal interfaces.

## 1. Product goal

SmartPark Edge must replace the current RFID-card workflow with a plate-first parking system that is faster, simpler, safer, easier to operate, and ready for mobile payment.

Current pain points:
- driver takes/scans/returns a card
- first 45 minutes free, then TZS 1,000 per additional 45-minute block
- kiosk payment is mandatory for paid stays
- no phone payment
- drivers reach toward machines and sometimes hit/brush equipment
- guards repeatedly assist
- current system is slow
- one gate computer is the server, the other gate is ~400 m away

New system:
- plate is primary identity
- no temporary RFID card required
- camera event creates the parking session
- payment can be kiosk or mobile
- paid/authorized plate opens any allowed exit automatically
- season/VIP/monthly/yearly vehicles auto-authorize by policy
- operator UI is clean and fast
- hardware is replaceable through adapters
- Windows is the primary production platform

---

## 2. Preserve the working HVX integration, but isolate it

The existing camera/gate integration now works because the legacy Windows files were reverse engineered. Treat it as a legacy hardware adapter, not as the architecture.

Never call HVX SDK functions from parking business services.

Use:

```python
class CameraAdapter:
    async def connect(self, device): ...
    async def health(self, device): ...
    async def snapshot(self, device): ...
    async def stream(self, device): ...
    async def subscribe_vehicle_events(self, device): ...
    async def capabilities(self, device): ...

class GateControllerAdapter:
    async def open(self, command): ...
    async def state(self): ...
    async def health(self): ...
```

Initial adapters:
- `HVXCameraAdapter`
- `HVXGateAdapter`
- `RTSPCameraAdapter`
- `ONVIFCameraAdapter`
- `SimulatedCameraAdapter`
- `SimulatedGateAdapter`

Future adapters can add Dahua, Axis, Hikvision, Modbus, PLC, HTTP relays, etc.

**ParkingService must never contain `if vendor == "HVX"` logic.**

---

## 3. Universal device registry

Store hardware as data:

```text
Device
- id
- site_id
- name
- device_type
- vendor
- model
- serial
- mac
- hardware_uuid
- ip / hostname
- port
- adapter_id
- credentials_reference
- gate_id
- lane_id
- enabled
- capabilities
- config
- health_state
- last_seen
```

Device types:
- CAMERA
- BARRIER
- PRINTER
- KIOSK
- DISPLAY
- SENSOR
- EDGE_AGENT

IP is mutable; stable hardware identity is preferred.

---

## 4. Site / Gate / Lane model

Do not hard-code two gates or four cameras.

```text
Site
├── Gate
│   ├── Lane ENTRY
│   └── Lane EXIT
└── Gate
    ├── Lane ENTRY
    └── Lane EXIT
```

Initial site has:
- Gate A entry/exit
- Gate B entry/exit
- four cameras
- corresponding barriers

Parking sessions are site-wide.

Valid:
- A→A
- A→B
- B→A
- B→B

---

## 5. Recommended site-server topology

Use the current stronger/server-side computer as the initial **SmartPark Site Server**, but do not encode its current gate name into software.

```text
                    INTERNET
                        |
                 Router/Firewall
                        |
                  Site LAN/Fiber
                        |
        +---------------+----------------+
        |                                |
 SmartPark Site Server              Gate B PC
        |                         Operator/Edge Agent
        |
        +-- PostgreSQL
        +-- FastAPI Site Core
        +-- workers
        +-- payment sync
        +-- device registry
        +-- HVX x86 SDK host if required
        +-- kiosk connection
```

V1:
- direct server-to-camera/gate integration is acceptable if reliable
- Gate B PC can remain an operator client

V2:
- support optional Gate Edge Agents
- `connection_mode = DIRECT | EDGE_AGENT`
- edge agents queue events locally and control local devices
- central PostgreSQL remains the business/financial authority

---

## 6. Plate-first entry

Primary casual flow:

```text
Vehicle approaches
→ camera/sensor triggers
→ plate is resolved
→ check active access entitlement
→ create ParkingSession in a short DB transaction
→ authorize entry
→ open barrier
```

Do not require card scanning.

### Receipt policy

Receipt is convenience, not identity.

Configurable:
- OFF
- PRINT_OPTIONAL
- PRINT_AND_OPEN
- REQUIRE_TAKEN_BEFORE_OPEN

Recommended initial policy: `PRINT_AND_OPEN`.

Receipt contains:
- site name/logo
- plate
- entry time
- entry gate
- public reference
- secure QR
- short payment instructions

Lost receipt is not fatal because the session is plate-based.

---

## 7. OCR confidence handling

Do not make uncertain OCR destroy traffic flow.

Configurable thresholds:
- HIGH → automatic
- MEDIUM → flag/review according to policy
- LOW → operator/manual fallback

Live Gate UI must show:
- full image
- plate crop
- raw native plate
- optional local OCR
- resolved plate
- confidence
- fast correction
- permitted manual open

Store corrections for future Tanzania OCR training.

---

## 8. Subscriber / Season / VIP model

Do not hard-code “season card”.

Use Access Plans:

Examples:
- Monthly Tenant
- Annual Tenant
- Staff
- VIP
- Contractor
- Fleet
- Exempt

Plan fields:
- start/end
- duration
- vehicle limit
- allowed days/times
- allowed gates
- receipt policy
- free/discount policy
- expiry grace
- auto-open
- anti-passback if required

Flow:

```text
plate
→ active entitlement?
→ create presence/session record
→ open immediately
```

Subscribers still create entry/exit history for occupancy/audit.

---

## 9. Parking-session state machine

Use explicit states:

```text
DETECTED
ENTRY_AUTHORIZED
ACTIVE
PAYMENT_PENDING
PAID
EXIT_AUTHORIZED
CLOSED
REVIEW_REQUIRED
CANCELLED
```

Store:
- plate
- entry gate/lane/time
- exit gate/lane/time
- customer/access type
- tariff version
- amount due
- payment summary
- authorization details

---

## 10. Flexible tariff engine

Do not hard-code 45 minutes / TZS 1,000.

Initial configuration may be:

```text
Grace: 45 minutes
Block: 45 minutes
Price: TZS 1,000
```

But support:
- day/night windows
- weekends
- holidays
- special events
- maximum daily fee
- overnight flat/block pricing
- discounts/exemptions
- effective dates
- payment-to-exit grace

Historical sessions keep the tariff version applied.

---

## 11. Fast exit flow

```text
exit camera detects plate
→ find ACTIVE site-wide session
→ recalculate fee
→ evaluate successful payment/access entitlement
→ if authorized:
     create exit authorization
     open correct exit barrier immediately
     close session after exit
  else:
     keep gate closed
     show PAYMENT REQUIRED
```

Gate decision must read local committed state, not wait on internet.

---

## 12. One unified payment ledger

Never model payment as only `paid = true`.

Create:
- PaymentProvider
- PaymentMethod
- PaymentIntent
- PaymentTransaction
- PaymentAllocation
- Refund

PaymentTransaction:

```text
id
site_id
session_id
intent_id
provider_id
method
amount
currency
status
provider_transaction_id
idempotency_key
operator_id
kiosk_id
created_at
confirmed_at
metadata
```

Statuses:
- CREATED
- PENDING
- SUCCEEDED
- FAILED
- EXPIRED
- REFUNDED
- PARTIALLY_REFUNDED

Kiosk and mobile payments use the same tables.

Session paid amount = successful payments minus refunds.

---

## 13. Payment methods

Support through configuration:

```text
MOBILE_MONEY_WEB
MOBILE_MONEY_PUSH
USSD_REFERENCE
KIOSK_CASH
KIOSK_MOBILE
POS_CARD
OTHER
```

Not every method must be enabled.

---

## 14. Smartphone payment

Entry QR opens a mobile-first public page:

```text
Plate: T453ETH
Entry: 12:18
Duration: 1h 24m
Amount Due: TZS 1,000
Status: UNPAID

[Pay with Mobile Money]
[Pay at Kiosk]
```

No app installation.

Public token must be:
- high entropy
- non-sequential
- not the plate
- not DB primary key
- unusable for admin/hardware APIs

---

## 15. Basic phone / no smartphone

Support these through `PaymentProvider`:

### A. Kiosk-triggered mobile-money collection
1. Find session by QR/plate.
2. Enter customer's phone number.
3. Create PaymentIntent.
4. Provider sends mobile-money approval request where supported.
5. User approves on basic phone.
6. Verified callback arrives.
7. Transaction becomes SUCCEEDED.
8. Print receipt.

### B. USSD/reference payment
If provider supports reliable reconciliation:
- display/print merchant instructions
- short payment/session reference
- exact amount
- provider callback/reconciliation confirms payment

### C. Kiosk cash
Kiosk Operator records permitted local payment and prints receipt.

All use the same payment ledger.

---

## 16. Payment provider abstraction

```python
class PaymentProvider:
    async def create_intent(self, request): ...
    async def initiate_collection(self, intent): ...
    async def verify_callback(self, request): ...
    async def query_status(self, provider_ref): ...
    async def refund(self, transaction): ...
```

Initial:
- SimulatedPaymentProvider
- ManualKioskPaymentProvider

Later:
- selected Tanzania mobile-money/aggregator adapter

Never hard-code a provider into ParkingService.

---

## 17. Payment security rule

A web/browser “success” response does **not** mean paid.

Mobile payment becomes `SUCCEEDED` only after:
- verified provider callback/webhook, or
- verified provider status query/reconciliation

Use:
- unique provider transaction ID
- idempotency
- callback authentication/signature verification
- expected amount/session validation
- duplicate callback handling

---

## 18. Fast mobile-payment-to-gate propagation

V1 architecture:

```text
Customer Phone
→ Public SmartPark URL
→ Payment Provider
→ verified callback
→ SmartPark Site Server
→ local PostgreSQL
→ exit camera decision
```

Expose only public payment/session endpoints through a secure reverse proxy/tunnel.

Never expose publicly:
- camera IPs
- PostgreSQL
- barrier control
- internal admin API
- SDK host

On successful payment:
1. verify callback
2. insert immutable PaymentTransaction
3. recompute session payment state
4. commit
5. create PAYMENT_CONFIRMED outbox event
6. update local exit authorization/cache
7. push WebSocket update to UI/kiosk/edge agent
8. do notifications/analytics later

---

## 19. Payment-to-exit grace

Configurable:
`payment_exit_grace_minutes`

Example:
- paid 13:00
- exit grace 15 min
- authorized through 13:15

If extra charges apply afterward, tariff engine handles them.

---

## 20. Kiosk

Kiosk is a client of Site API, not financial authority.

Flow:

```text
Scan QR / Enter Plate
→ lookup session
→ calculate fee
→ select method
→ create payment
→ confirmation
→ print receipt
```

Cash/local payment records:
- operator
- kiosk
- shift
- amount
- receipt
- timestamp
- audit trail

Kiosk UI should be full-screen and extremely simple.

---

## 21. Windows-first desktop UI

Recommended navigation:

```text
OVERVIEW
- Dashboard
- Live Gates

OPERATIONS
- Parking Sessions
- Vehicles
- Payments
- Subscribers
- Kiosk

MANAGEMENT
- Reports
- Tariffs & Schedules

SYSTEM
- Devices
- Users & Roles
- Audit Logs
- Settings
```

Hardware Lab is restricted to Admin/Technician permissions.

Normal operator pages must not show SDK/RTSP/raw JSON/developer instructions.

---

## 22. Dashboard

Cards:
- Vehicles Inside
- Entries Today
- Exits Today
- Revenue Today
- Unpaid Active Sessions
- Subscribers Inside

Show lane/device health and actionable alerts.

---

## 23. Roles and permissions

Built-in:
- ADMIN
- OPERATOR
- KIOSK_OPERATOR

Use granular permissions, e.g.:

```text
dashboard.view
gates.view
gates.open_manual
gates.emergency_open
sessions.view
sessions.correct_plate
payments.view
payments.create
payments.refund
subscribers.manage
tariffs.manage
devices.manage
users.manage
roles.manage
settings.manage
audit.view
hardware.commission
```

Permissions must be enforced in backend APIs, not only hidden in UI.

Admin CRUD:
- users
- roles
- permissions
- activate/deactivate
- reset password
- force logout
- lock/unlock

Never permanently erase historical operator identity from audit/payment records.

---

## 24. Security

Mandatory:
- secure password hashing
- RBAC server-side
- idle lock/session expiry
- login rate limiting
- encrypted secrets
- HTTPS public endpoints
- verified payment callbacks
- no camera/payment secrets in frontend/logs
- secure backup
- manual gate-open audit
- no public GPIO/gate endpoint

---

## 25. Branding and appearance

White-label settings:
- app display name
- site name
- logo
- icon
- accent color
- support contact
- receipt header/footer

Themes:
- SYSTEM
- LIGHT
- DARK

Use semantic theme tokens; do not hard-code one mall or brand.

---

## 26. Performance requirements

Critical local path:

```text
camera event
→ normalized detection
→ indexed DB lookup / short transaction
→ access decision
→ gate command
```

Never wait for:
- SMS
- cloud analytics
- reports
- receipt rendering
- payment provider during entry
- image archival

Instrument:
- detection latency
- recognition latency
- DB decision latency
- gate command latency
- total authorization latency

Aim for sub-second local authorization where hardware permits; measure real performance.

---

## 27. Reliability

Assume:
- duplicate camera events
- duplicate payment callbacks
- network delay
- Gate B link interruption
- internet outage
- camera restart
- printer failure
- server restart
- DB deadlock
- repeated manual open

Implement:
- idempotency
- unique event/transaction/command IDs
- short DB transactions
- transactional outbox
- durable queues
- bounded retry/backoff
- structured logs
- correlation IDs
- device health states

Never hold DB locks during gate, printer, camera, or provider I/O.

---

## 28. Core data model

At minimum:

```text
Site
Gate
Lane
Device
CameraConfiguration
BarrierConfiguration

User
Role
Permission
UserRole
RolePermission

Vehicle
ParkingSession
VehicleDetection
AccessDecision
GateCommand

Customer
SubscriptionPlan
Subscription
SubscriptionVehicle

TariffPlan
TariffVersion
TariffRule
ScheduleWindow

PaymentProvider
PaymentMethod
PaymentIntent
PaymentTransaction
Refund

Receipt
Kiosk
KioskShift

AuditLog
OutboxEvent
SystemSetting
BrandingSetting
```

Production DB: PostgreSQL.

---

## 29. Commissioning modes

Per lane:
- COMMISSIONING
- SHADOW
- PRODUCTION
- MAINTENANCE

Only authorized Admin can change mode.

SHADOW:
- real detections and decisions
- no automatic physical gate control

---

## 30. Windows packaging

Production must support:
- Windows 10/11 x64
- SmartPark x64 desktop/site service
- x86 HVX SDK host where legacy SDK requires it
- installer
- Windows services/background startup
- platform-safe app-data/log paths
- upgrade/migration strategy

Ubuntu can remain a development platform.

---

## 31. Development order

1. Preserve the current working HVX camera/gate integration as adapters.
2. Build Site/Gate/Lane/Device Registry.
3. Build plate event → session → gate flow.
4. Build Windows operations desktop.
5. Build RBAC/audit.
6. Build tariff engine.
7. Build subscribers/season/VIP.
8. Build unified kiosk/payment ledger.
9. Build public QR page.
10. Add real mobile-money provider later.
11. Add generic ONVIF/RTSP/new-vendor onboarding.
12. Add optional Gate B Edge Agent/resilience.

Do not replace working cameras or build cloud microservices before V1 works.

---

# 32. Documentation is a mandatory product deliverable

Create:

```text
docs/
  00-START-HERE.md
  01-PRODUCT-VISION.md
  02-CURRENT-SITE-TOPOLOGY.md
  03-SYSTEM-ARCHITECTURE.md
  04-DOMAIN-MODEL.md
  05-DATABASE-SCHEMA.md
  06-SESSION-STATE-MACHINE.md
  07-HARDWARE-ADAPTER-ARCHITECTURE.md
  08-HVX-CAMERA-INTEGRATION.md
  09-HVX-GATE-INTEGRATION.md
  10-ADDING-A-NEW-CAMERA-VENDOR.md
  11-ADDING-A-NEW-GATE-CONTROLLER.md
  12-RECOGNITION-PIPELINE.md
  13-TARIFF-ENGINE.md
  14-PAYMENT-ARCHITECTURE.md
  15-ADDING-A-PAYMENT-PROVIDER.md
  16-KIOSK-FLOW.md
  17-PUBLIC-QR-PAYMENT-SITE.md
  18-SUBSCRIBERS-SEASON-VIP.md
  19-USERS-ROLES-PERMISSIONS.md
  20-DESKTOP-UI-UX.md
  21-API-REFERENCE.md
  22-SECURITY-MODEL.md
  23-RELIABILITY-IDEMPOTENCY-OUTBOX.md
  24-WINDOWS-DEPLOYMENT.md
  25-SITE-NETWORKING.md
  26-BACKUP-RESTORE.md
  27-LOGGING-MONITORING.md
  28-TESTING-STRATEGY.md
  29-COMMISSIONING-GUIDE.md
  30-TROUBLESHOOTING.md
  31-INCIDENT-RECOVERY.md
  32-CONTRIBUTING.md
  33-VIBE-CODER-PLAYBOOK.md
  ADR/
```

Every major document must contain:
1. Purpose
2. Responsibility/owner
3. What it must NOT do
4. Diagram
5. Data structures
6. Request/event flow
7. Failure behavior
8. Security
9. Configuration
10. Tests
11. Extension guide
12. Common mistakes

Use Mermaid diagrams.

---

## 33. HVX docs are especially important

Because the current hardware integration required reverse engineering, document:
- exact SDK/OCX/runtime requirements
- x86 host boundary
- discovery/connect flow
- camera ports/configuration
- plate callbacks
- snapshot/video/RTSP
- reconnect behavior
- exact adapter interfaces
- known limitations
- diagnostic commands
- verified gate-control mechanism
- gate/channel mappings
- commissioning procedure
- rollback procedure

No future developer should reverse engineer the same files again.

---

## 34. Vibe-coder playbook

`33-VIBE-CODER-PLAYBOOK.md` must be procedural.

Example — new camera:

```text
1. Do NOT edit ParkingService.
2. Implement CameraAdapter.
3. Declare capabilities.
4. Register adapter.
5. Add config schema.
6. Add Hardware Lab UI.
7. Pass adapter contract tests.
8. Shadow-test it.
```

New payment provider:

```text
1. Implement PaymentProvider.
2. Never trust browser success.
3. Verify provider callback.
4. Enforce transaction idempotency.
5. Add sandbox/integration tests.
6. Reconcile a real payment before production.
```

Tariff changes:
- use tariff configuration
- never edit code constants

---

## 35. Architecture Decision Records

Create ADRs such as:

```text
ADR-001-Plate-Is-Primary-Identity.md
ADR-002-PostgreSQL-Is-Site-Authority.md
ADR-003-Hardware-Uses-Adapters.md
ADR-004-Payment-Uses-Immutable-Transactions.md
ADR-005-Windows-First-HVX-SDK-Host.md
ADR-006-Public-Payment-Endpoints-Are-Separate.md
ADR-007-Receipt-Is-Not-Primary-Identity.md
```

---

## 36. Recommended repository boundaries

```text
smartpark/
  desktop/
  api/
  domain/
  application/
  infrastructure/
    db/
    hardware/
      cameras/
        hvx/
        rtsp/
        onvif/
      gates/
        hvx/
      printers/
    payments/
    messaging/
  workers/
  public_web/
  kiosk/
  common/

tools/
  hvx_sdk_host/
  diagnostics/

tests/
  unit/
  integration/
  hardware_contract/
  e2e/

docs/
```

Adapt names to the existing codebase but preserve boundaries.

---

## 37. Non-negotiable invariants

1. Plate/session identity does not depend on RFID.
2. Camera vendor code does not own parking rules.
3. Gate vendor code does not own tariff/payment rules.
4. Mobile payment is paid only after verified confirmation.
5. Kiosk and mobile use one payment ledger.
6. Entry and exit gates can differ.
7. RBAC is enforced server-side.
8. Public web cannot control gates.
9. Internet failure cannot corrupt local parking state.
10. Historical tariff/payment/audit data remains explainable.
11. Manual gate opens are audited.
12. Normal UI does not expose reverse-engineering details.

---

## 38. Definition of V1 success

V1 is ready when:
- all four HVX cameras work through `HVXCameraAdapter`
- all existing booms work through `HVXGateAdapter`
- casual entry requires no RFID
- plate automatically creates session
- operator can correct plate quickly
- current tariff works as configuration
- kiosk payment records into unified ledger
- paid vehicle exits through either gate
- unpaid vehicle is denied automatic exit
- subscriber/season/VIP plates auto-authorize
- entry receipt/QR can print if enabled
- public mobile page shows session/fee
- PaymentProvider abstraction exists
- RBAC/audit work
- Windows restart restores services/config
- hardware failures are observable
- docs are complete enough for another developer or AI-assisted developer to continue safely

---

# Final instruction to Cursor

Treat the working HVX integration as a legacy adapter that proves the real hardware can be controlled.

The product itself is:

```text
Vehicle detection
→ Parking session
→ Tariff/access decision
→ Payment
→ Exit authorization
→ Gate command
```

Everything hardware/provider-specific plugs into that flow through adapters.

Optimize the local gate path for speed. Keep mobile payments trustworthy. Support smartphone QR, basic-phone payment workflows, kiosk payment, subscribers and VIPs through shared domain models.

Make the software Windows-first, modern, branded, themeable, permission-aware and operationally simple.

Finally, create and maintain the entire `/docs` tree above. Documentation is part of the product, not an afterthought.
