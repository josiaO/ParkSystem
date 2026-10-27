# SmartPark Database Configuration

## Supported databases

- **PostgreSQL** is the recommended production database for a multi-workstation site.
- **SQLite** is supported for development, demonstrations, Camera Lab, temporary field testing and single-computer evaluation.

For the managed PostgreSQL installation procedure, official download links, service checks, role creation and the complete do/don’t checklist, see [POSTGRESQL-PREREQUISITE.md](POSTGRESQL-PREREQUISITE.md).

The approved Windows package does not bundle a PostgreSQL server. The deployment wizard therefore connects to an existing PostgreSQL installation and tests it before applying the configuration. It never downloads software during a normal or offline installation.

## Architecture

```text
Operator Workstation → SmartPark API → Site Server → PostgreSQL
```

Operator Workstations never connect directly to PostgreSQL. PostgreSQL should normally listen on the Site Server only; do not open TCP 5432 to operator PCs.

## SQLite setup

Select **Site Server**, then **SQLite — testing / evaluation** in Deployment Configuration. Acknowledge the warning. SmartPark creates the data directory and database, runs the Alembic migrations, checks integrity/WAL/read-write behavior and creates the first administrator.

On Windows the default location is:

```text
C:\ProgramData\SmartParkEdge\smartpark.db
```

SQLite is not recommended for concurrent multi-workstation production use. Do not copy a live WAL database with Explorer; stop SmartPark and use the site backup procedure.

## PostgreSQL setup

Install PostgreSQL separately using the site’s approved offline package, then create a database and user with permission to create and migrate the SmartPark schema. In the wizard enter:

- server: normally `127.0.0.1`
- port: `5432`
- database: `smartpark`
- username and password

The wizard checks host resolution, TCP reachability, authentication, database access, permissions and a transaction. Apply runs Alembic to the current head before the Site Service starts. If PostgreSQL is missing or unreachable, the wizard reports that PostgreSQL could not be reached and offers SQLite for evaluation.

The password is not written to `deployment.json`. On Windows it is stored through the DPAPI-backed SmartPark secret store and the deployment file keeps only a secret reference. Do not put a password in logs, screenshots or support exports.

## Migration

Alembic is owned by the Site Server. Operator Workstations never run migrations. A fresh database is initialized; an existing database is upgraded to head. A migration failure prevents the Site Service from starting and leaves the deployment unconfigured/recovery-required.

SQLite-to-PostgreSQL migration is not presented as an automatic wizard operation in this release. Preserve the SQLite source and use a tested migration procedure before changing a live site.

## Backup and restore

The Windows kit has a site backup reminder and an offline download action. SQLite uses a consistent SQLite backup snapshot before producing SQL. PostgreSQL uses the matching `pg_dump` tool from the approved PostgreSQL installation, with the password supplied process-locally rather than as a command-line argument. Verify the backup before changing the live database. PostgreSQL restore remains an administrator-led recovery procedure using `pg_restore`/`psql`; it is not silently performed by an Operator Workstation.

Before restore: stop SmartPark writes, take a backup of the current database, validate the selected backup, restore, verify the Alembic revision and health-check the Site Service. Do not start parking against an unknown schema.

## Troubleshooting

- **PostgreSQL service stopped:** start the approved PostgreSQL Windows service and rerun Test Database.
- **Port 5432 unavailable:** verify the PostgreSQL port and local firewall; the SmartPark API does not require 5432 from operator PCs.
- **Authentication failed:** verify the database user/password and its database permissions.
- **Database missing:** create the configured database or select SQLite for testing.
- **Migration pending:** run Deployment Configuration on the Site Server; never run it on a workstation.
- **Disk full:** stop writes, free disk, then run the database and backup checks again.
- **SQLite locked:** close duplicate Site Services, preserve the database, and restart only the Site Server after the lock is cleared.

## Health metadata

The Site Server exposes `/health/database` with engine, state, revision, head, migration status and latency. It never exposes a password or credential-bearing URL.

## Security

Keep PostgreSQL local to the Site Server whenever possible. Allow operator clients to reach TCP 8760 and, when WebRTC is enabled, TCP 8889 and UDP/TCP 8189 on the private LAN. Keep PostgreSQL 5432, MediaMTX control 9997, metrics 9998, internal RTSP 8554 and the HVX host 8765 internal.
