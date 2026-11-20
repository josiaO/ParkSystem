# Linked vehicles, fleets and visitor passes

Registered vehicles can belong to a **group**. A group limits how many of its
cars can be inside at the same time.

| Group kind | Typical use | Cars inside at once |
|---|---|---|
| **Private** | One owner, several cars, one parking place | Always exactly 1 |
| **Fleet** | A company with N reserved places | N (0 means no limit) |

The second car of a private owner is refused at the entry while the first is
inside. Guards see who a car belongs to, e.g. *Company: ACME Logistics Ltd*
or *Private: J. Obeid*, in the Vehicles table, the refusal message and the
exit lookup.

**Visitor passes** let a host admit a guest's plate for a time window and a
number of entries, without registering the car.

## When does a car count as "left"?

This matters because a group place is only freed once Zirp is sure the car has
gone. Each group chooses how strict to be:

| Exit evidence | Normal (exit lane) | Strict (passage confirmed) |
|---|---|---|
| Loop or beam saw the car pass | frees the place | frees the place |
| Exit camera identified the car and the barrier accepted the command | frees the place | keeps it locked |
| A guard confirmed it left (with photo and reason) | frees the place | frees the place |
| A supervisor reconciled it | frees the place | frees the place |
| The same car shows up at the entry again | frees the place | frees the place |
| The barrier was opened by hand | **nothing changes** | **nothing changes** |

A hand-opened barrier never frees a place, because Zirp can't know which car
went through.

## When Zirp isn't sure

If a visit ends without good evidence, the place stays locked as *exit
unconfirmed*. To sort it out:

1. A guard opens **Sessions → Confirm vehicle left…**, finds the visit by
   receipt QR, session number or plate, and looks at the entry photo.
2. They pick **The vehicle has left** (the place is freed) or **I am not sure**
   (it goes to a supervisor). A reason is required.
3. A supervisor uses **Reconcile (supervisor)…** to release the place or keep
   the car inside.

Every step is logged with who did it and why.

## Permissions

| Permission | Who has it by default |
|---|---|
| `exits.confirm` | Operator, Supervisor |
| `exits.reconcile` | Supervisor |
| `visitors.manage` | Operator, Supervisor |

Admins have everything.

## Under the hood

Each group place is a row with a unique index on *(group, place) while not
released*, so two lanes racing for the last place can't both win. We test this
on PostgreSQL with lanes entering simultaneously, ten rounds in a row.
