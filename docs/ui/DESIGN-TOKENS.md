# Design tokens

The web UI keeps the existing SmartPark palette. Do not replace teal, add gradients, or change the type stack.

## Light

| Token | Value |
| --- | --- |
| Background | `#F2F4F6` |
| Surface | `#FFFFFF` |
| Surface alt | `#F7F9FB` |
| Text primary | `#161C24` |
| Text secondary | `#545E6C` |
| Border | `#E2E6EC` |
| Accent | `#0E7C72` |
| Accent strong | `#0B6A61` |
| Success | `#17784B` |
| Warning | `#A05A0B` |
| Danger | `#C0372E` |
| Info | `#2B6CB0` |

## Dark

| Token | Value |
| --- | --- |
| Background | `#0D1117` |
| Surface | `#151B22` |
| Surface alt | `#1A222B` |
| Text primary | `#E7EDF3` |
| Text secondary | `#9AA5B1` |
| Accent | `#2FBFAD` |
| Accent strong | `#4ACEBD` |
| Success | `#41B879` |
| Warning | `#E0A23E` |
| Danger | `#E4584E` |
| Info | `#5CA3E4` |

CSS variables live in `app/web/index.html` (`--bg`, `--surface`, `--accent`, and the status colors).

## Status chips

| Class | Meaning |
| --- | --- |
| `c-ok` | Healthy, online, paid, ready |
| `c-wrn` | Degraded, pending, check plate |
| `c-dgr` | Offline, unpaid, failed |
| `c-info` | Informational, refunded |
| `c-mut` | Disabled or unknown. Neutral, not an error |

Status is also written as text. Color is not the only signal.

## Layout

- Sidebar 236px, 210px below 1400px, 58px when collapsed.
- Primary operator target is a desktop browser from 1366×768 upward.
- Focus uses a 2px accent outline.
