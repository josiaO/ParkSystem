# Zirp documentation

Start with the question you have:

| I want to... | Read |
|---|---|
| Install Zirp, update it, or roll back | [install.md](install.md) |
| Connect a camera, fix a black picture, calibrate where cars are read | [cameras.md](cameras.md) |
| Wire barriers and ground loops, open a barrier by hand, set up owner alerts | [gates-and-loops.md](gates-and-loops.md) |
| Look up the loop board UDP protocol | [loop-boards.md](loop-boards.md) |
| Take cash, mobile money (ClickPesa) or kiosk payments | [payments.md](payments.md) |
| Set up private cars, company fleets or visitor passes | [vehicle-groups.md](vehicle-groups.md) |
| Set up PostgreSQL, back up and restore | [database.md](database.md) |
| Check services, read logs, recover from a failure | [operations.md](operations.md) |
| Understand how the system is built | [architecture.md](architecture.md) |
| Work on the code, run tests, build and release the installer | [development.md](development.md) |

Reports:

- [audit-2026-11.md](audit-2026-11.md): the November 2026 production audit:
  what we tested, what we fixed, and what still needs on-site hardware checks.

Component READMEs:

- [tools/hvx_sdk_host](../tools/hvx_sdk_host/README.md): the 32-bit camera SDK host
- [portal](../portal/README.md): the Next.js back office and pay page
- [research/parkwatch](../research/parkwatch/README.md): notes on the vendor
  system Zirp replaces, including its camera protocol
