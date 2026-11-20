# Payments

Zirp takes payment in three ways:

- **Cash** at a cashier desk or an attended kiosk
- **Mobile money** (M-Pesa, Mixx by Yas, Airtel Money, HaloPesa) through **ClickPesa**,
  our only mobile-money provider
- **Pay page**: the driver scans the QR code on the receipt and pays from their
  phone

Cash and the kiosk work with no internet at all. Mobile money obviously needs
the internet, but if it drops, cash still works and exits keep running.

## How a payment is recorded

Every payment ends up as one row in an append-only ledger. The rules that keep
the money right:

- **The server computes the amount.** A browser or phone never says how much
  to charge. Zirp works out what's outstanding on the visit and asks for
  exactly that.
- **A provider payment is recorded once.** Each one is keyed on ClickPesa's
  own transaction ID and on our request reference. A webhook that arrives
  twice, a webhook plus a status check, or two at the same moment still give
  one ledger entry. We test that against PostgreSQL with 8 simultaneous
  deliveries.
- **Webhooks are verified.** The checksum is checked and Zirp then asks
  ClickPesa for the payment status itself. Amount, currency and reference must
  all match what we requested.
- **Cash is confirmed by a person.** Only a signed-in operator can record cash.
  A double click on "paid" is recognised and recorded once.

## Exit grace

After paying, a driver gets time to walk back and drive to the exit without
being charged again: **15 minutes** by default. Change it under **Settings →
Parking rules**. Set it to 0 to re-quote at the exit. If the grace runs out,
the visit reopens and the extra time is charged.

## Setting up ClickPesa

Get the client ID, API key and checksum key from your ClickPesa dashboard, then
enter them under **Settings → Mobile money** in the desktop app, or in
`C:\ProgramData\SmartParkEdge\config\zirp.env`:

```
SMARTPARK_PAYMENTS_MOBILE_PROVIDER=clickpesa
SMARTPARK_CLICKPESA_CLIENT_ID=...
SMARTPARK_CLICKPESA_API_KEY=...
SMARTPARK_CLICKPESA_CHECKSUM_KEY=...
SMARTPARK_PUBLIC_BASE_URL=https://pay.your-site.co.tz
```

ClickPesa needs to reach the webhook, so the pay page and
`/api/webhooks/clickpesa` must be reachable from the internet through
`SMARTPARK_PUBLIC_BASE_URL`. Everything else stays on the LAN.

### Switching on real money

Keys alone don't collect money. That's deliberate, so a test setup can't charge
anyone by accident. The **Mobile money** tab shows the mode:

| Mode | Meaning |
|---|---|
| `UNCONFIGURED` | No keys yet |
| `MOCK` | Pointed at a test server; no real money can move |
| `LIVE_DISABLED` | Keys saved, real collection still switched off |
| `LIVE` | Real payments |

To go live, set both of these:

```
SMARTPARK_CLICKPESA_LIVE_ENABLED=true
SMARTPARK_PAYMENTS_LIVE_PROVIDER_CONFIRMED=true
```

Restart the services after changing `zirp.env`.

## Testing without real money

We ship a ClickPesa mock with the same API, a fake phone where you approve or
decline the USSD push, and switches for late, duplicated or forged webhooks:

```powershell
cd "C:\Program Files\Zirp\current"
.\python64\python.exe -m app.mock_services.clickpesa --port 9100
.\python64\python.exe -m app.cli env preset mock-payments
```

Open `http://127.0.0.1:9100/phone` to play the driver and
`http://127.0.0.1:9100/admin` to inject faults.

## Receipts

The entry receipt carries a QR code tied to the visit. Scanning it at a cashier
desk or kiosk finds the visit straight away. Scanning it with a phone opens the
pay page. Entry photos aren't shown on the public receipt page by default.
