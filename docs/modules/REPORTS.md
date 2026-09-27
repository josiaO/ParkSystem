# REPORTS Module

`GET /reports/summary` returns an audit pack for a date range:

- overview of visits, money, average stay, and plate-reading accuracy
- payment lines
- cars still inside or still owing
- takings by day and cash by operator
- native vs local plate agreement and operator corrections
- manual barrier opens and plate corrections
- season tickets, including those expired or ending within 14 days

`GET /reports/export.csv?kind=` downloads one of those tables. `kind=payments` is the same file as `GET /reports/payments.csv`. The browser Reports page and the desktop Reports page print and download this pack.

Plate-reading totals count stored captures only. They do not change how a plate is accepted or how a gate opens.

Backup lives beside reports:

- `GET /backup/download` saves a SQL copy on this computer and clears the offline reminder
- `PATCH /backup` sets how often to be reminded, and an optional cloud address plus interval
- `POST /backup/cloud` sends that SQL file to the configured address
- the dashboard shows a reminder until an offline copy is saved or the reminder is snoozed

Cloud backup only runs when an operator turns it on and sets an `http` or `https` address.
