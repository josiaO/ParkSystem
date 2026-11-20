# Barriers, ground loops and manual opening

## How a barrier gets opened

Zirp lifts a barrier only after the decision to let the car through is safely
written to the database. In order:

1. A camera reads the plate (it must pass the camera's calibration, see
   [cameras.md](cameras.md)).
2. Zirp decides: new visit, registered vehicle, paid exit, and so on.
3. The decision and a **barrier command with its own ID** are saved together in
   one database transaction.
4. Only then does the command go to the barrier.
5. The barrier's answer is saved against that same command: `ACCEPTED` or
   `FAILED`.

What this buys you:

- **A power cut can't open a barrier for a car Zirp has no record of.** If the
  PC dies between steps 3 and 5, the command is marked `INTERRUPTED` after a
  minute and shows up for an operator. Zirp doesn't silently re-send it.
- **One decision lifts the barrier once.** Repeats of the same command, for
  example a retry after a network hiccup, never pulse the barrier a second
  time. A failed command can still be retried.
- **Old camera frames never open anything.** A plate read from a frame older
  than about 2 seconds is ignored.
- **Exits check the money first.** The exit decision reads the payment ledger in
  the same transaction, so a car only leaves when its visit is paid (or free,
  or within the exit grace after paying).

## What counts as a barrier

Only real actuators count: the camera's relay output and the network I/O
boards. LED displays are display-only. A sign that answers doesn't mean the
barrier moved, and Zirp never treats it that way.

## Ground loops and I/O boards

Each lane side can have a small network I/O board with the ground loop, ticket
button and barrier relay wired to it. Zirp listens for the boards itself on
**UDP port 8000**. The frame format, event codes and wiring are in
[loop-boards.md](loop-boards.md).

When a lane has a loop, a visit moves on when the car actually drives over it.
Without one, Zirp can treat an accepted barrier command as "car passed" or wait
for a time-out. That's the lane's passage setting.

## Opening a barrier by hand

Operators can open a barrier from **Live Gates** (*Manual open*, F8) or from a
visit (*Admit without receipt*). Every manual opening is recorded with:

- who opened it and the reason they typed (a reason is required),
- the plate last seen on that lane and a photo,
- the visit it belongs to and how much was still owed.

If the barrier goes up and Zirp didn't command it (someone pressed the button
on the barrier or used the vendor remote), Zirp notices this on the boards that
report it and records an **uncommanded opening**.

### Alerts for manual openings

Manual openings can send an SMS, email or webhook to the site owner. Set the
recipients in **Settings → Alerts**:

- Unidentified cars and openings where money was owed always alert.
- Openings with nothing owed alert too, unless you turn that off.
- Failed commands alert only if you ask for it.

Alerts are queued in the database and retried with back-off (up to 8 attempts
by default), so a down internet link only delays them. An alert also isn't lost
if the server stops right after the opening: the delivery loop picks up any
opening whose alerts weren't queued yet.

SMS goes through Africa's Talking and email through your SMTP server. Set them
in `zirp.env`:

```
SMARTPARK_ALERTS_AFRICASTALKING_USERNAME=...
SMARTPARK_ALERTS_AFRICASTALKING_API_KEY=...
SMARTPARK_ALERTS_SMTP_HOST=smtp.example.com
SMARTPARK_ALERTS_SMTP_USERNAME=...
SMARTPARK_ALERTS_SMTP_PASSWORD=...
SMARTPARK_ALERTS_SMTP_FROM=parking@example.com
```

## Linked vehicles and fleets

Private owners with several cars and company fleets can share a limited number
of "inside" places. That's covered in [vehicle-groups.md](vehicle-groups.md).
