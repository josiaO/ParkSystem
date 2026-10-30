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

## If PostgreSQL is already installed: do this in order

Installing PostgreSQL is only the first step. Zirp still needs a running Windows service, a database, a dedicated login and a successful connection test. The following commands can be run from **CMD as Administrator**. They do not configure Zirp by themselves; after the database checks pass, use the Zirp Deployment Configuration wizard so the password is stored in Windows DPAPI.

### 1. Find and start the PostgreSQL service

```cmd
sc query type= service state= all | findstr /I "postgres"
```

The service name normally looks like `postgresql-x64-17`; the major version may be different. Start the exact name shown by the command:

```cmd
net start postgresql-x64-17
```

If `net start` says the service name is invalid, repeat the first command and use the installed version. If the service is already running, continue. Do not start a second PostgreSQL instance.

### 2. Find `psql` and verify the port

```cmd
where psql
psql --version
netstat -ano | findstr ":5432"
powershell -NoProfile -Command "Test-NetConnection 127.0.0.1 -Port 5432"
```

If `where psql` finds nothing, use the full path. PostgreSQL commonly installs it below `C:\Program Files\PostgreSQL\<major>\bin`:

```cmd
set "PG_BIN=C:\Program Files\PostgreSQL\17\bin"
"%PG_BIN%\psql.exe" --version
```

Replace `17` with the major version installed on the PC. `TcpTestSucceeded : True` means that something is listening on the port; it does not yet prove that the Zirp login or database is correct.

### 3. Create the Zirp database and dedicated login

Open an interactive administrator session. The password is requested by `psql`; do not put it in the command line.

```cmd
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

At the `postgres=#` prompt, run:

```sql
CREATE ROLE smartpark LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE smartpark OWNER smartpark;
\password smartpark
\q
```

Use the site’s password manager for the password entered by `\password`. If either `CREATE` statement reports that the role or database already exists, stop and inspect ownership instead of running it again:

```cmd
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

```sql
SELECT rolname, rolcanlogin, rolsuper FROM pg_roles WHERE rolname = 'smartpark';
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname = 'smartpark';
\q
```

The `smartpark` role must be allowed to log in, must not be a superuser, and should own the `smartpark` database. A database administrator should use `ALTER ROLE`, `ALTER DATABASE` or the approved grant procedure when correcting an existing installation.

### 4. Test the exact Zirp credentials

```cmd
"%PG_BIN%\psql.exe" -h 127.0.0.1 -p 5432 -U smartpark -d smartpark -c "select current_user, current_database();"
```

Enter the password when prompted. The expected result contains `smartpark | smartpark`. If this command fails, do not continue to the Zirp wizard: fix the service, port, role, password or `pg_hba.conf` first.

### 5. Configure Zirp and run migrations

1. Start **Zirp** and open **Deployment Configuration**.
2. Choose **Site Server**.
3. On **Database**, choose **PostgreSQL — recommended for production**.
4. Enter `127.0.0.1`, port `5432`, database `smartpark`, username `smartpark` and the password just tested.
5. Press **Test Database** and wait for every check to show `PASS`.
6. Continue, create the first Zirp administrator, review the site values and choose **Apply**.
7. Confirm `http://127.0.0.1:8760/health/database` reports a healthy PostgreSQL connection and restart Zirp if the wizard requests it.

The wizard runs the Zirp migrations and stores only a protected secret reference in `deployment.json`. Do not paste the password into a ticket, screenshot, permanent environment variable or command history.

### CMD-only diagnostic fallback

CMD is useful for provisioning PostgreSQL and testing it. It is not the preferred way to save the Zirp database password because a full connection URL can expose that password in process listings and history. For a one-process diagnostic only, use a URL with a URL-encoded password and close the CMD window afterward:

```cmd
set "SMARTPARK_DATABASE_URL=postgresql+psycopg://smartpark:URL_ENCODED_PASSWORD@127.0.0.1:5432/smartpark"
```

Use the Deployment Configuration wizard for the real installation; it validates migrations and uses the protected Windows secret store.

## Technician installation procedure on Windows

1. Download PostgreSQL from the official Windows installer page above, or obtain the approved offline installer from the site software administrator.
2. Run the installer with administrator approval. Install PostgreSQL Server as a Windows service. pgAdmin is optional; it is useful for administration but is not required by SmartPark.
3. Use the default PostgreSQL TCP port `5432` unless the site already has a conflict. If a different port is selected, record it for the SmartPark wizard.
4. Set a strong PostgreSQL administrator password. Store it in the site password manager. This is a provisioning credential; SmartPark must not use it for daily database access.
5. Keep the database listening on `127.0.0.1` when PostgreSQL is installed on the Site Server. Only configure a LAN listener when the site has an approved remote database design.
6. Confirm the PostgreSQL Windows service is running and that the configured port is reachable locally.
7. Create the SmartPark database and dedicated login described below.
8. Open SmartPark Deployment Configuration, select **Site Server**, select **PostgreSQL**, enter the database values, select **Test Database**, then apply the configuration.

For a Processing Node, do not install or select SQLite. Start the Site Server
first, run `Install-SmartPark.bat` on the node PC and choose `EDGE_NODE`, then enter the Site Server's
LAN address when asked for the Site Server connection, and enter that same
server's PostgreSQL host, port, database and dedicated login. The node tests
the existing schema but does not initialize a local database, run migrations or
create an administrator. PostgreSQL must therefore be configured to accept the
node PC's private-network address in `listen_addresses`, `pg_hba.conf` and the
Windows firewall; never expose port 5432 to the whole network.

### Important: PostgreSQL is installed on the Site Server, not the node

Do **not** install a second PostgreSQL Server on the Processing Node. That would
create a different database on the node and the node would no longer be using
the Site Server's authoritative database. The node only needs:

- the Zirp Processing Node installation;
- a network route to the Site Server;
- the Site Server PostgreSQL host address and port; and
- a dedicated PostgreSQL login/password that the node is allowed to use.

The Zirp Windows package includes the Python PostgreSQL driver used by the
wizard and service. A separate `psql.exe` client is optional and is not the
same thing as installing a PostgreSQL Server.

Assume the following example values and replace them with the actual values:

```text
Site Server IPv4 address: 192.168.10.20
Processing Node IPv4 address: 192.168.10.21
PostgreSQL port: 5432
Database: smartpark
Database login: smartpark
Site Server API: http://192.168.10.20:8760
```

#### Configure the Site Server for the node

Run these checks on the Site Server:

1. Find the server's private IPv4 address:

   ```cmd
   ipconfig
   ```

   Use the IPv4 address of the LAN adapter, not `127.0.0.1` and not a VPN
   address. Give the server a DHCP reservation or another stable address.

2. Find the PostgreSQL data directory. It is normally:

   ```text
   C:\Program Files\PostgreSQL\<major>\data
   ```

   The two files to edit are `postgresql.conf` and `pg_hba.conf`. If the
   installed service uses another data directory, inspect it in the PostgreSQL
   service's executable path or use pgAdmin's server configuration view.

3. In `postgresql.conf`, set the listener to the Site Server LAN address and
   localhost. Do not use `0.0.0.0` unless the site firewall is carefully
   restricted:

   ```conf
   listen_addresses = '192.168.10.20,127.0.0.1'
   port = 5432
   ```

4. At the bottom of `pg_hba.conf`, add one rule for each Processing Node. Use
   the node's fixed IPv4 address with `/32` so only that computer is allowed:

   ```conf
   host    smartpark    smartpark    192.168.10.21/32    scram-sha-256
   ```

   Add more `/32` lines for additional nodes. Do not add `0.0.0.0/0`,
   `192.168.10.0/24` or `trust` as a shortcut. The database and login names in
   this rule must exactly match the values used in the node wizard.

5. Allow TCP 5432 from the node in **Windows Defender Firewall**. From an
   elevated CMD on the Site Server:

   ```cmd
   netsh advfirewall firewall add rule name="Zirp PostgreSQL from node 192.168.10.21" dir=in action=allow protocol=TCP localport=5432 remoteip=192.168.10.21 profile=Private
   ```

   For more than one node, create one restricted rule per node, or use the
   approved node subnet. Do not select `Any` remote address.

6. Restart PostgreSQL so `listen_addresses` is applied. Use the exact service
   name shown by the first command:

   ```cmd
   sc query type= service state= all | findstr /I "postgres"
   net stop postgresql-x64-17
   net start postgresql-x64-17
   ```

   Replace `postgresql-x64-17` with the installed service name. Confirm it is
   running:

   ```cmd
   netstat -ano | findstr ":5432"
   ```

7. Make sure the Site Server API is also reachable from the node. The node
   wizard tests `http://192.168.10.20:8760`; TCP 8760 must be allowed by the
   private-network firewall rule created for Zirp.

#### Test from the Processing Node

Run these commands on the node in CMD or PowerShell. These tests do not require
installing PostgreSQL Server on the node:

```cmd
ping 192.168.10.20
powershell -NoProfile -Command "Test-NetConnection 192.168.10.20 -Port 8760"
powershell -NoProfile -Command "Test-NetConnection 192.168.10.20 -Port 5432"
```

Expected results:

- port `8760` is reachable, proving the node can contact the Zirp API;
- port `5432` is reachable, proving the firewall/listener path is open.

`TcpTestSucceeded : True` only proves that TCP is open. It does not prove the
PostgreSQL password or database rule is correct. The Zirp wizard performs the
real authentication and schema test.

#### Enter the node wizard values

On the Processing Node PC:

1. Run `Install-SmartPark.bat` and choose `EDGE_NODE`.
2. On **Site Server connection**, enter `http://192.168.10.20:8760` and press
   **Test Connection**. The identity must show the expected site server.
3. On **Database**, PostgreSQL is forced. Enter:

   ```text
   Database server: 192.168.10.20
   Port:            5432
   Database name:   smartpark
   Username:        smartpark
   Password:        the password assigned to the smartpark login
   ```

   Never enter `127.0.0.1` or `localhost` here: those addresses mean the node
   PC itself, not the Site Server.

4. Press **Test Database**. It must report authentication, database access and
   current schema as `PASS`. A node must not run migrations; if the schema is
   behind, run the upgrade from the Site Server and test the node again.
5. Finish setup, sign in with the Zirp user created on the Site Server using
   the **Processing Node** role, then assign the node to its gate.

#### What each failure means

| Failure | Likely cause | Fix |
|---|---|---|
| Site Server connection fails | API address or TCP 8760 blocked | Use the server LAN IP with `:8760`; allow the Zirp API on the Private firewall profile |
| Port 5432 test fails | PostgreSQL listens only on localhost, firewall blocked, wrong IP, or service stopped | Check `listen_addresses`, restart PostgreSQL, and add the restricted firewall rule |
| Authentication failed | Wrong username/password or `pg_hba.conf` mismatch | Test the exact role on the server, reset its password with `\\password smartpark`, and verify the `/32` rule |
| Database does not exist | Node points to the wrong database name | Use the database created on the Site Server, normally `smartpark` |
| Schema is not current | Site Server has not completed setup/migrations | Run **Test Database/Apply** on the Site Server first; never migrate from the node |
| Node connects to the wrong computer | Node database host is `localhost` or `127.0.0.1` | Replace it with the Site Server's private IPv4 address |

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
CREATE ROLE smartpark
  LOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOBYPASSRLS;

CREATE DATABASE smartpark OWNER smartpark;
```

Set the login password using the password prompt rather than putting it in shell history:

```sql
\password smartpark
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
- Use a dedicated `smartpark`-style login with `NOSUPERUSER` and no role/database administration privileges.
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
