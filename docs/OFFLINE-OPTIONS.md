# When gate B loses the link to the Site Server: options

Design note only. Nothing in this document is implemented beyond "Today".

## Today

Gate B (an Edge Node about 400 m from the Site Server) runs its own Site
Service, cameras, worker and barrier, but every parking decision reads and
writes the Site Server's PostgreSQL. When that link drops:

* requests fail within about 5 s (connect timeout, 5 s pool wait, 15 s
  statement timeout) with HTTP 503 and the instruction "use the receipt QR at
  the kiosk, or call an operator";
* the desktop shows a red "Server link down" banner on every gate PC that
  cannot reach the database, and `/health/live` reports `db_link`;
* recognition events are kept in gate B's local outbox and processed when the
  link returns; events older than 20 s are stored for review, never used to
  open a barrier;
* **no barrier opens automatically at gate B**: no entry session can be
  created and no exit can be checked. Operators open manually and note plates.

### Field test of the current behaviour

On the gate B PC (elevated PowerShell):

```powershell
# Dropped link: block PostgreSQL to the Site Server
New-NetFirewallRule -DisplayName "TEST block PostgreSQL" -Direction Outbound -RemotePort 5432 -Protocol TCP -Action Block
# ... drive a car to the exit; expect the red banner within ~10 s and a closed barrier
Remove-NetFirewallRule -DisplayName "TEST block PostgreSQL"
```

For a slow link, add latency with a network emulator (for example `clumsy` on
Windows or `tc qdisc add dev eth0 root netem delay 3000ms` on a Linux router)
and check that the banner turns amber or red and the desktop stays usable.

## The question

Which is the smallest change that lets gate B keep working through a link
outage, and what does each option cost?

## Option A: read replica of the Site Server database at gate B

PostgreSQL streaming replication to a hot standby on gate B. During an outage
gate B reads the replica (read-only).

What it can do offline:
* **exit of an already-paid or still-free visit**: look up the session and its
  payments on the replica and open the barrier;
* registered vehicles (season/staff) at entry and exit.

What it cannot do offline:
* **create entry sessions** (the replica is read-only), so casual entries at
  gate B still need an operator;
* record the exit/close a session, take cash, or accept new payments; these
  writes must be queued and replayed, which reintroduces a small outbox anyway;
* see payments made after the link dropped (mobile payments arrive at the Site
  Server).

Risks and cost:
* replica lag: a payment made seconds before the outage may be missing, so
  the driver is refused and must use the QR/kiosk;
* a second PostgreSQL to install, monitor and upgrade on a gate PC; failover
  logic in the Site Service (which database to read for which decision);
* a car that exits at B offline and re-enters at A before replay could look
  "still inside" at A; needs a rule for that.

Effort: moderate infrastructure work, small code change (read routing for
exit lookups), plus a replay path for the exit/close writes.

## Option B: local outbox with UUID session identities

Gate B keeps a local store; entries and exits made offline are written locally
with globally unique IDs and synchronised to the Site Server when the link
returns.

What it can do offline:
* **create casual entry sessions** (print a receipt with a UUID-based token);
* exit visits that **entered at gate B** during the outage (known locally);
* registered vehicles if the registry is cached locally.

What it cannot do offline:
* exit a car that entered at gate A (its session is only on the Site Server),
  unless a replica/cache of open sessions is also kept, which is Option A again;
* verify mobile payments.

Risks and cost:
* the database keys are integers today; sessions, receipts and payments must
  move to UUIDs (a schema migration touching every parking table) or carry a
  separate global ID;
* conflict rules: the same plate entering at A online and at B offline; a
  session closed in two places; receipt token collisions are avoided by
  randomness, but human references are not;
* the "one open session per plate per site" guarantee becomes eventual during
  an outage;
* a sync protocol with idempotent upload, retry and conflict reporting.

Effort: large. It touches the parking engine, the schema and the payment
reconciliation, and needs careful testing of the merge rules.

## Comparison

| | A: read replica | B: outbox + UUID sessions |
|---|---|---|
| Paid/free exits for cars that entered at A | Yes | No |
| New casual entries at B | No | Yes |
| Exits for cars that entered at B offline | Only if paid before the outage | Yes |
| Schema change | None | Large (UUIDs or global IDs) |
| New infrastructure | Standby PostgreSQL on gate B | Local store + sync service |
| Main risk | Stale payments (lag) | Merge conflicts, eventual uniqueness |
| Effort | Moderate | Large |

## Recommendation

Mall traffic at an exit is mostly paid or free visits leaving, and stranded
paying drivers are the expensive failure. Option A protects that case with no
schema change, and the read-only path keeps the "plate is identity, recognition
is evidence" rule intact. Start with Option A for exits plus the existing
operator fallback for entries; revisit Option B only if field data shows gate B
outages long and frequent enough that manual entries are a real burden.

Before either: measure the link. Record `db_link` state changes from
`/health/live` on gate B for a few weeks. If outages are rare and short, the
current fail-fast behaviour plus the operator fallback may be enough.
