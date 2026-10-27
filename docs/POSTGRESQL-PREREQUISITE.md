# PostgreSQL prerequisite for SmartPark Edge

SmartPark Edge uses the managed/prerequisite PostgreSQL approach for production. PostgreSQL is installed and started as a normal system service; SmartPark connects to it, validates it and owns the SmartPark schema and migrations. PostgreSQL binaries are not bundled in the SmartPark package.

## Official resources

- [PostgreSQL Windows installers](https://www.postgresql.org/download/windows/) — the official download page links to the certified EDB Windows installer.
- [PostgreSQL documentation](https://www.postgresql.org/docs/current/) — installation, administration, roles, authentication and backup reference.
- [PostgreSQL connection settings](https://www.postgresql.org/docs/current/runtime-config-connection.html) — `listen_addresses` and `port`.
- [PostgreSQL roles](https://www.postgresql.org/docs/current/sql-createrole.html) — `LOGIN`, `NOSUPERUSER` and role privileges.
- [PostgreSQL client authentication](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) — `pg_hba.conf` and SCRAM authentication.
- [PostgreSQL `pg_dump`](https://www.postgresql.org/docs/current/app-pgdump.html) — consistent logical database exports.

Use the PostgreSQL major version approved for the SmartPark release. Do not upgrade the major version on a live site without a backup, a tested restore and a release-compatibility check.

## Technician installation procedure on Windows

1. Download PostgreSQL from the official Windows installer page above, or obtain the approved offline installer from the site software administrator.
2. Run the installer with administrator approval. Install PostgreSQL Server as a Windows service. pgAdmin is optional; it is useful for administration but is not required by SmartPark.
3. Use the default PostgreSQL TCP port `5432` unless the site already has a conflict. If a different port is selected, record it for the SmartPark wizard.
4. Set a strong PostgreSQL administrator password. Store it in the site password manager. This is a provisioning credential; SmartPark must not use it for daily database access.
5. Keep the database listening on `127.0.0.1` when PostgreSQL is installed on the Site Server. Only configure a LAN listener when the site has an approved remote database design.
6. Confirm the PostgreSQL Windows service is running and that the configured port is reachable locally.
7. Create the SmartPark database and dedicated login described below.
8. Open SmartPark Deployment Configuration, select **Site Server**, select **PostgreSQL**, enter the database values, select **Test Database**, then apply the configuration.

Example checks from an elevated PowerShell prompt:

```powershell
Get-Service -Name "postgresql*" | Select-Object Name, Status, StartType
Test-NetConnection -ComputerName 127.0.0.1 -Port 5432
```

Expected result: the PostgreSQL service is `Running`, its startup type is automatic or the site’s approved equivalent, and `TcpTestSucceeded` is `True`.

## Create the dedicated SmartPark database and login

The PostgreSQL administrator performs the one-time provisioning. The SmartPark application login should not be `postgres`, `root` or another superuser.

Connect to the maintenance database as the PostgreSQL administrator using pgAdmin or `psql`, then run the following statements. Replace only the database and role names if the site has an approved naming standard:

```sql
CREATE ROLE smartpark_app
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOBYPASSRLS;

CREATE DATABASE smartpark OWNER smartpark_app;
```

Set the login password using the password prompt rather than putting it in shell history:

```sql
\password smartpark_app
```

If the role or database already exists, do not run `CREATE` blindly. Ask the database administrator to verify ownership, login status, connection privilege and password, then use the appropriate `ALTER ROLE` or `GRANT` operation.

SmartPark applies its own Alembic migrations after the connection test. The technician does not need to create SmartPark tables manually.

## Authentication and network rules

- Prefer `scram-sha-256` password authentication for TCP connections.
- Keep PostgreSQL bound to localhost when the Site Server is the database host.
- Do not add `0.0.0.0/0`, the whole LAN or an unapproved address range to `pg_hba.conf`.
- Do not use `trust` authentication for production. PostgreSQL documents that `trust` permits any host that can connect to log in as any database user without a password.
- Do not open TCP `5432` to Operator Workstations. Operator Workstations use the SmartPark API on TCP `8760`.
- If PostgreSQL must be remote, document the approved client subnet, use TLS according to the site security policy, and restrict `pg_hba.conf` and the network firewall together.

## SmartPark wizard values

| Field | Local PostgreSQL default | What to enter |
|---|---|---|
| Database server | `127.0.0.1` | The approved PostgreSQL host name or address |
| Port | `5432` | The PostgreSQL service port |
| Database name | `smartpark` | The database provisioned for this site |
| Username | `smartpark` | The dedicated SmartPark login, not `postgres` |
| Password | blank until entered | The dedicated login password; SmartPark stores a protected secret reference |

The password is not written to `deployment.json`. On Windows it is stored through the DPAPI-backed SmartPark secret store. During a later reconfiguration, leaving the password field blank reuses the existing protected secret; enter a new value only when rotating the database password.

## Backup and upgrade rules

- Back up before SmartPark upgrades, PostgreSQL upgrades, schema changes or hardware replacement.
- Use the matching PostgreSQL `pg_dump`/`pg_restore` tools and inspect warnings from the dump command.
- Verify that a backup can be read or restored in a controlled environment before relying on it.
- Keep the backup, the SmartPark release identifier and the non-secret deployment metadata together.
- Never delete the live database to fix a migration problem.
- Never restore an untrusted dump into production without inspecting it; PostgreSQL warns that restore operations can execute code contained in the source dump.

## Do and do not checklist

### Do

- Install PostgreSQL before running the SmartPark Site Server wizard.
- Use the PostgreSQL major version approved for the release.
- Use a dedicated `smartpark_app`-style login with `NOSUPERUSER` and no role/database administration privileges.
- Keep PostgreSQL local to the Site Server whenever possible.
- Use a stable Site Server address for Operator Workstations.
- Run **Test Database** before applying the SmartPark configuration.
- Keep the PostgreSQL administrator credential and SmartPark database credential separate.
- Rotate credentials through the site’s password-management process and re-test SmartPark afterward.
- Back up and verify the database before changes.

### Do not

- Do not expect SmartPark to download or install PostgreSQL automatically.
- Do not use the `postgres` superuser for normal SmartPark operation.
- Do not use `trust` authentication in production.
- Do not expose PostgreSQL `5432` to Operator Workstations or the public Internet.
- Do not put the PostgreSQL password in `deployment.json`, screenshots, logs, support exports, shell arguments or source control.
- Do not manually edit SmartPark SQL tables or run migrations from an Operator Workstation.
- Do not use SQLite for a multi-workstation production site.
- Do not copy a live SQLite or PostgreSQL data directory as a backup.
- Do not start a second PostgreSQL instance on the same port.
- Do not change PostgreSQL major versions or SmartPark database drivers on site without a tested release procedure.

## Troubleshooting

- **PostgreSQL is not reachable:** confirm the Windows service, host, port and local firewall, then run **Test Database** again.
- **Authentication failed:** verify the dedicated login password and `pg_hba.conf`; do not switch to `trust` as a workaround.
- **Database does not exist:** ask the PostgreSQL administrator to create `smartpark` or use the site’s approved database name.
- **Permission/migration failure:** verify that the dedicated login owns the database or has the approved migration permissions. Do not use a superuser without approval.
- **Port conflict:** identify the existing service using the port, choose the approved PostgreSQL port or update the SmartPark wizard to the existing service port. Do not start a second database on the same port.
- **SmartPark is not ready after setup:** check `/health/database`, the Site Service log and the Alembic revision before changing the database.
