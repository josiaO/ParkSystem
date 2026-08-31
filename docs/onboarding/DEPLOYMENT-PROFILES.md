# Deployment Profiles

| Profile | Use case | Key modules |
|---------|----------|-------------|
| `LPR_ONLY` | Plate logging, exports | cameras, media, recognition, reports |
| `SECURITY` | Watchlists, alerts | + security.* |
| `ACCESS_CONTROL` | Registered vehicles, gates | access, subscribers |
| `PARKING_LITE` | Single entry/exit parking | + parking, tariffs, payments.kiosk |
| `PARKING_PRO` | Multi-gate, kiosks, public pay | + kiosk, payments.public_web |
| `ENTERPRISE` | All modules | ALL |
| `CUSTOM` | Manual selection | operator-defined |

Apply via Admin **Setup Wizard** (web) or `PUT /modules/profile`.

Existing installs default to `PARKING_LITE` so behavior is unchanged until you switch profiles.
