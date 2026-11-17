# Zirp portal

A separate Next.js front end for the existing Zirp Site Service (FastAPI). Nothing in the lane runtime depends on it.

- **Public pay page** (`/p/<ticket code>`, `/s/<code>` from the receipt QR): mobile first, English/Swahili. Drivers pay with mobile money (M-Pesa, Mixx by Yas, Airtel Money, HaloPesa), then the page follows the payment live until it's confirmed. A banner shows when the site uses a test provider.
- **Back office** (`/admin`): sign in with a Zirp account. It shows today's overview, lanes, sessions, the payment ledger, the payment provider's health (including the "MOCK" badge), pending-payment reconciliation, reports and CSV exports.

The portal holds no data and no secrets. It calls the Site Service API from the server side. The operator's API token lives in an httpOnly cookie and is never visible to page scripts. Provider webhooks pass through byte for byte, so the Site Service still verifies their checksums.

## Start it

Needs Node.js 20 or newer and a running Zirp Site Service.

```bash
./start-portal.sh --api http://127.0.0.1:8760        # Linux/macOS
```

```bat
start-portal.bat --api http://127.0.0.1:8760          :: Windows
```

The first run creates `.env.local`, installs packages and builds. Later runs just start. After updating the code, use `--rebuild`. Then open `http://<this machine>:3000`.

| Setting (`.env.local`) | Meaning |
|---|---|
| `ZIRP_API_URL` | Where the Site Service API listens, as seen from this machine. **Required.** |
| `ZIRP_SITE_NAME` | Name in the header and browser tab. |
| `PORT` | Port for `npm start` (default 3000). |
| `ZIRP_SECURE_COOKIES` | `true` when the portal is served over HTTPS. |
| `ZIRP_SUPPORT_PHONE` | Optional help line on the pay page. |

`npm run check` validates `.env.local` and confirms that the API answers. Changing a setting needs a restart, not a rebuild.

## Make receipts open the portal

In Zirp, set the public base URL to the portal's address, for example `https://pay.example.co.tz` or `http://192.168.10.240:3000` on a LAN. Printed QR codes then open `/s/<code>` on the portal.

When going live with a real provider, register the portal URL as the webhook URL: `https://<portal>/api/webhooks/clickpesa`.

## Mobile payments without real money

Run the whole flow on one PC:

1. Switch Zirp to the mock provider. This generates test credentials and never touches real money:
   `python -m app.cli env preset mock-payments --lan-ip <this PC's IP> --restart`
   On Windows kits, use `SmartPark-Settings.bat preset mock-payments --lan-ip <IP> --restart`.
2. Start the mock ClickPesa: `python -m app.mock_services.clickpesa --host 0.0.0.0`, or `Start-MockPayments.bat`.
3. Start the portal: `start-portal.bat` / `./start-portal.sh`.
4. Open a receipt (`http://<IP>:3000/p/<code>`), enter any number such as `0712 345 678`, and press **Pay**.
5. Open the mock phone at `http://<IP>:9100/phone` and choose **Approve**, **Decline** or **Reverse**. The pay page updates by itself.
6. `http://<IP>:9100/admin` rehearses provider faults: late, dropped, duplicated or forged webhooks, underpayment, and outages.

The provider runs in **MOCK** mode whenever its base URL is a private host (loopback, LAN address, or a `.test`/`.local` name). A real ClickPesa host still needs the explicit live flags, so "LIVE" always means real money.

## Run it as a service (Linux)

```ini
# /etc/systemd/system/zirp-portal.service
[Unit]
Description=Zirp portal
After=network-online.target

[Service]
WorkingDirectory=/opt/zirp/portal
EnvironmentFile=/opt/zirp/portal/.env.local
ExecStart=/usr/bin/npx next start
Restart=on-failure
User=zirp

[Install]
WantedBy=multi-user.target
```

Put a TLS reverse proxy (Caddy or nginx) in front of it for anything reachable from the internet.
