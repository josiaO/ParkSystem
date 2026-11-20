# Database

PostgreSQL on the Site Server is the single source of truth for a site:
visits, payments, barrier commands, cameras, users and settings. Every PC on
the site talks to that one database over the LAN, and nothing important lives
only on a lane PC.

SQLite is supported for development and single-PC demos. Don't use it for a
real site.

## Setting up PostgreSQL

Zirp doesn't install PostgreSQL. Install it on the Site Server first (we run
PostgreSQL 18 from the official Windows installer), then create a database and
a login for Zirp:

```sql
CREATE ROLE smartpark LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE smartpark OWNER smartpark;
```

Edge Nodes and workstations connect over the LAN, so allow the Site Server's
subnet in `pg_hba.conf`, for example:

```
host  smartpark  smartpark  192.168.1.0/24  scram-sha-256
```

Then run the Zirp setup wizard (it opens on first start). It asks for host,
port, database and user, tests the connection, and stores the password
encrypted with Windows DPAPI, never in a plain settings file.

## Schema updates (migrations)

You don't run migrations by hand. When the Site Service starts it brings the
database to the newest schema:

- an empty database gets all tables created and is marked current,
- an older database is upgraded step by step with Alembic.

Installer updates take a database backup before this happens, and switch back
to the previous version if the new one doesn't come up healthy.

## Backups

| Backup | When | Where |
|---|---|---|
| Pre-update dump | Automatically before every update | `C:\ProgramData\SmartParkEdge\backups\pre-upgrade` (last 5 kept) |
| Manual dump | `zirpctl backup` | same folder |
| Offline copy | Desktop **Backup** page: save to a USB drive; Zirp reminds you when it's overdue | where you save it |
| Cloud copy | Optional, scheduled (24 h by default), **Backup** page | your backup URL |

Manual backup from an administrator PowerShell:

```powershell
& "C:\Program Files\Zirp\bin\zirpctl.ps1" backup -Label before-maintenance
```

### Restoring

Restore runs as **one transaction**: either the whole backup goes in, or the
database is left exactly as it was. A damaged or truncated backup file can't
leave you with half a database. Before restoring, Zirp also saves the current
database next to the backup.

```powershell
cd "C:\Program Files\Zirp\current"
.\python64\python.exe -m app.release_tool restore --in "C:\ProgramData\SmartParkEdge\backups\pre-upgrade\<file>.sql" --yes
```

Stop the Zirp services first (`zirpctl services stop`) and start them again
afterwards. To go back to the database from before the last update in one step,
use `zirpctl rollback -RestoreDatabase` instead.

## When the database link drops

Connections are set to fail fast, so a dead link is noticed in seconds instead
of hanging a lane, and they reconnect when the link is back. Work that has to
reach the database later, such as plate events, payment confirmations and
alerts, sits in durable outboxes and is retried. Check the link from any PC:

```
http://<site-server-ip>:8760/health/database
```
