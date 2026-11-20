# Installing and updating Zirp

Zirp ships as one Windows installer, `Zirp-Setup-<version>.exe`. It carries
everything it needs: Python, the recognition models, the camera SDK, FFmpeg,
MediaMTX and the web portal. You don't need Python, Node or Git on the site PC,
and you don't need internet during installation.

**Download:** grab the latest installer from the
[Releases page](https://github.com/josiaO/ParkSystem/releases). Each release
also has a `.sha256` file so you can check the download is intact:

```powershell
Get-FileHash .\Zirp-Setup-1.0.0-rc4.exe -Algorithm SHA256
```

The hash should match the one in the `.sha256` file and in the release notes.

> Builds are not code-signed yet, so Windows SmartScreen may say "Unknown
> publisher" the first time. Click **More info → Run anyway** after you've
> checked the hash.

## Before you start

| You need | Why |
|---|---|
| Windows 10 (1809 or later) or Windows 11, 64-bit | The installer refuses older systems. |
| An administrator account | Zirp installs per machine and registers Windows services. |
| PostgreSQL on the Site Server | The site database (we run PostgreSQL 18). Zirp doesn't install PostgreSQL for you; see [database.md](database.md). |
| 2 GB free disk at least | Photos and database backups grow over time; plan for more. |
| A fixed LAN IP for the Site Server | Every other PC, camera and kiosk talks to it. |

Everything runs on the local network. Internet is only needed for mobile-money
payments (ClickPesa) and optional cloud backups, and even without it gates,
kiosks, cash and exits keep working.

## Pick a role

The installer asks what this computer does on the site:

| Role in the installer | What it runs | Use it for |
|---|---|---|
| **Site Server with cameras and gates** | Site Service, media, recognition, camera SDK host, portal | A small site where one PC does everything |
| **Site Server only** | Site Service, portal | The central server when lanes have their own Edge Nodes |
| **Edge Node** | Site Service, media, recognition, camera SDK host | A lane PC wired to cameras and barriers |
| **Operator Workstation** | Desktop app only | Cashier and supervisor desks |
| **Payment Kiosk** | Full-screen kiosk app | The driver-facing pay station |

For a kiosk, the installer asks which Windows account runs it. Use a dedicated
standard (non-admin) account that signs in automatically. Zirp starts full
screen when that account signs in and comes back if someone closes it.

For roles with cameras, you also choose how the 32-bit camera SDK host runs:
as a Windows service (works with nobody signed in) or when a user signs in. Use
the service option only once the camera model has been tested that way on site.

## First install

1. Run the installer as administrator.
2. Pick the role (see above) and click through.
3. The installer copies the files, registers the services and waits until
   Zirp answers its health check. The first start creates the database
   tables, so give it a minute or two.
4. Open **Zirp** from the Start menu. On a fresh site the setup wizard walks
   you through the database connection, the server network address and the
   first administrator account.

## Updating or repairing

Run the newer installer on the PC. When Zirp is already installed it asks:

- **Update to Zirp x.y.z (keep role and settings)**: the normal choice.
- **Repair Zirp x.y.z**: shown when you run the same version again. It puts
  the program files back without touching your settings.
- **Change the role or options of this computer**: shows the role pages again
  before updating.

During an update the installer:

1. stops the Zirp services,
2. backs up the database (`C:\ProgramData\SmartParkEdge\backups\pre-upgrade`),
3. installs the new version next to the old one,
4. switches over and checks Zirp is healthy,
5. **switches back to the previous version automatically** if it isn't.

Your settings, database, photos and payment keys live in
`C:\ProgramData\SmartParkEdge` and are never replaced by an update.

### Silent install for IT

```powershell
.\Zirp-Setup-1.0.0-rc4.exe /VERYSILENT /ROLE=OPERATOR
```

Add `/RECONFIGURE=1` to show the role pages again on an update.

### Installing other PCs on the LAN

Once a Site Server is installed it keeps a copy of its installer and serves it
to the rest of the site, so you don't need a USB stick:

```
http://<site-server-ip>:8760/downloads/zirp-setup.exe
```

There's also a link on the web sign-in page.

## Where things go

```
C:\Program Files\Zirp\
    versions\<version>\     one complete release per folder
    current                 points at the active version (every service uses it)
    bin\zirpctl.ps1         the control tool
C:\ProgramData\SmartParkEdge\
    config\zirp.env         site settings (ClickPesa keys, camera options, ...)
    config\portal.env       portal settings
    backups\pre-upgrade\    database dump taken before every update
    logs\                   service logs, install logs
```

## Rolling back

If something is wrong after an update, go back to the previous version from an
administrator PowerShell:

```powershell
& "C:\Program Files\Zirp\bin\zirpctl.ps1" rollback
```

That changes the program only. To also put the database back the way it was
before the update (this throws away visits and payments recorded since):

```powershell
& "C:\Program Files\Zirp\bin\zirpctl.ps1" rollback -RestoreDatabase
```

More `zirpctl` commands are in [operations.md](operations.md).

## Uninstalling

Use **Settings → Apps → Zirp → Uninstall**. Services, tasks, firewall rules and
program files are removed. Site data in `C:\ProgramData\SmartParkEdge` stays:

- On an Operator or Kiosk PC you're asked whether to delete it (default: no).
- On a Server or Edge Node it's never deleted automatically, because the site
  database references the photos stored there. For a full factory reset run
  `zirpctl purge-data -Force` before uninstalling.

## Next steps

- Connect the cameras: [cameras.md](cameras.md)
- Wire the barriers and ground loops: [gates-and-loops.md](gates-and-loops.md)
- Set up payments: [payments.md](payments.md)
