"""Read, set and check Zirp settings in the ``.env`` file, safely.

    python -m app.cli env list [--filter payment] [--changed]
    python -m app.cli env get CLICKPESA_BASE_URL
    python -m app.cli env set PUBLIC_BASE_URL=https://pay.example.co.tz SITE_NAME="Rock City Mall"
    python -m app.cli env unset CLICKPESA_BASE_URL
    python -m app.cli env check
    python -m app.cli env preset mock-payments [--lan-ip 192.168.10.240]
    python -m app.cli env template > default.env.example
    python -m app.cli env restart

Names may be written with or without ``SMARTPARK_`` and in any case.
Values are validated against the setting's type before anything is written;
the file keeps its comments and order, and the previous copy is saved as
``.env.bak``. Secrets (keys, passwords, tokens) are never printed in full.
Services read ``.env`` at start: restart them afterwards (``--restart`` on
Windows does it for you, without admin rights).
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PREFIX = "SMARTPARK_"
_SECRET_HINTS = ("password", "secret", "api_key", "_key", "token", "hash", "credential")
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")

# Settings that belong together, for ``env list --filter <group>``.
GROUPS = {
    "payment": ("payments_", "clickpesa_", "flutterwave_", "mobile_money", "kiosk_cash", "public_base_url"),
    "alerts": ("alerts_",),
    "camera": ("hvx_", "camera", "coil_", "gpio_", "detect_", "alpr_", "recognition_", "native_"),
    "database": ("database_", "db_", "postgres"),
    "site": ("site_", "public_base_url", "deployment_", "node_", "api_", "currency", "timezone"),
}

SERVICES_STOP_ORDER = ("SmartParkRecognitionWorker", "SmartParkMediaService", "SmartParkSiteService")


def _settings_class():
    from app.config import Settings

    return Settings


def env_file_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    from app.config import install_directory

    return install_directory() / ".env"


def field_names() -> dict[str, Any]:
    return dict(_settings_class().model_fields)


def canonical(name: str) -> str:
    """'clickpesa_base_url', 'SMARTPARK_CLICKPESA_BASE_URL' -> 'clickpesa_base_url'."""
    key = str(name or "").strip()
    if key.upper().startswith(PREFIX):
        key = key[len(PREFIX):]
    key = key.lower()
    if key not in field_names():
        close = [f for f in field_names() if key and (key in f or f in key)][:5]
        hint = f" Did you mean: {', '.join(PREFIX + c.upper() for c in close)}?" if close else ""
        raise KeyError(f"Unknown setting '{name}'.{hint}")
    return key


def env_key(field: str) -> str:
    return PREFIX + field.upper()


def is_secret(field: str) -> bool:
    info = field_names().get(field)
    if info is not None and info.annotation in (bool, int, float):
        return False                      # flags and numbers are never secrets
    lowered = field.lower()
    if lowered.endswith(("_url", "_enabled", "_seconds", "_minutes", "_hours", "_port", "_required", "_confirmed")):
        return False
    return any(hint in lowered for hint in _SECRET_HINTS)


def mask(field: str, value: Any) -> str:
    text = "" if value is None else str(value)
    if not text or not is_secret(field):
        return text
    return f"set ({len(text)} chars, ends ...{text[-2:]})" if len(text) > 6 else "set"


def validate(field: str, raw: str) -> Any:
    """Validate a value with the setting's own type and validators."""
    from pydantic import ValidationError

    Settings = _settings_class()
    try:
        instance = Settings.model_validate({field: raw}) if raw != "" else None
    except ValidationError as exc:
        problems = "; ".join(str(err.get("msg") or "invalid value") for err in exc.errors())
        raise ValueError(f"{env_key(field)}: {problems}") from None
    return getattr(instance, field) if instance is not None else ""


# -- .env file ---------------------------------------------------------------
def _quote(value: str) -> str:
    if value == "" or re.search(r"[\s#'\"=]", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner
    return re.sub(r"\s+#.*$", "", value)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = _LINE.match(line)
        if match and not line.lstrip().startswith("#"):
            values[match.group(1).upper()] = _unquote(match.group(2))
    return values


def write_env(path: Path, updates: dict[str, str | None]) -> None:
    """Set (str) or remove (None) keys, keeping comments and order. Atomic."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    pending = {key.upper(): value for key, value in updates.items()}
    out: list[str] = []
    for line in lines:
        match = _LINE.match(line)
        key = match.group(1).upper() if match and not line.lstrip().startswith("#") else None
        if key in pending:
            value = pending.pop(key)
            if value is not None:
                out.append(f"{key}={_quote(value)}")
            continue
        out.append(line)
    added = [(k, v) for k, v in pending.items() if v is not None]
    if added:
        if out and out[-1].strip():
            out.append("")
        out.extend(f"{key}={_quote(value)}" for key, value in added)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    if os.name != "nt":
        os.chmod(path, 0o600)


def current_values(path: Path) -> dict[str, tuple[Any, str]]:
    """field -> (value, source) where source is env | file | default."""
    file_values = read_env(path)
    result: dict[str, tuple[Any, str]] = {}
    for field, info in field_names().items():
        key = env_key(field)
        if key in os.environ:
            result[field] = (os.environ[key], "process env")
        elif key in file_values:
            result[field] = (file_values[key], "file")
        else:
            default = info.default if info.default is not None else ""
            result[field] = (default if not callable(default) else "", "default")
    return result


# -- commands ----------------------------------------------------------------
def cmd_list(path: Path, *, filter_text: str = "", changed: bool = False) -> int:
    values = current_values(path)
    prefixes = GROUPS.get(filter_text.lower()) if filter_text else None
    print(f"# {path}")
    for field in sorted(values):
        value, source = values[field]
        if changed and source == "default":
            continue
        if prefixes is not None and not any(p in field for p in prefixes):
            continue
        if filter_text and prefixes is None and filter_text.lower() not in field:
            continue
        shown = mask(field, value)
        print(f"{env_key(field):48} {shown!s:40} [{source}]")
    return 0


def cmd_get(path: Path, name: str, *, reveal: bool = False) -> int:
    field = canonical(name)
    value, source = current_values(path)[field]
    print(f"{env_key(field)}={value if reveal else mask(field, value)}   [{source}]")
    return 0


def cmd_set(path: Path, assignments: list[str]) -> int:
    updates: dict[str, str] = {}
    for item in assignments:
        if "=" not in item:
            raise ValueError(f"Use NAME=VALUE (got '{item}')")
        name, raw = item.split("=", 1)
        field = canonical(name)
        validate(field, raw.strip())
        updates[env_key(field)] = raw.strip()
    write_env(path, updates)
    for key, value in updates.items():
        print(f"set {key}={mask(key[len(PREFIX):].lower(), value)}")
    shadowed = [k for k in updates if k in os.environ]
    if shadowed:
        print("note: also set in this process's environment, which wins over the file: " + ", ".join(shadowed))
    return 0


def cmd_unset(path: Path, names: list[str]) -> int:
    keys = [env_key(canonical(name)) for name in names]
    write_env(path, {key: None for key in keys})
    for key in keys:
        print(f"removed {key} (default applies)")
    return 0


def cmd_check(path: Path) -> int:
    """Validate every value in the file and summarise payment readiness."""
    problems, warnings = [], []
    file_values = read_env(path)
    known = {env_key(f) for f in field_names()}
    for key, raw in file_values.items():
        if not key.startswith(PREFIX):
            continue
        if key not in known:
            warnings.append(f"{key}: not a Zirp setting (ignored)")
            continue
        try:
            validate(key[len(PREFIX):].lower(), raw)
        except ValueError as exc:
            problems.append(str(exc))
    from app.config import Settings

    try:
        effective = Settings(_env_file=str(path)) if path.exists() else Settings()
    except Exception as exc:  # cross-field validation
        problems.append(f"settings do not load: {exc}")
        effective = None
    if effective is not None:
        summary = payment_summary(effective)
        print(f"payments: provider={summary['provider']} mode={summary['mode']} real_money={summary['real_money']}")
        warnings.extend(summary["warnings"])
    for line in warnings:
        print("WARN ", line)
    for line in problems:
        print("ERROR", line)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def payment_summary(cfg) -> dict[str, Any]:
    from app.infrastructure.payments.clickpesa import is_mock_host

    provider = str(cfg.payments_mobile_provider or "simulated").lower()
    warnings: list[str] = []
    mode = "SIMULATED"
    if provider == "clickpesa":
        if not (cfg.clickpesa_client_id and cfg.clickpesa_api_key):
            mode = "UNCONFIGURED"
            warnings.append("ClickPesa: CLIENT_ID / API_KEY not set")
        elif is_mock_host(cfg.clickpesa_base_url):
            mode = "MOCK"
        elif cfg.clickpesa_live_enabled and (cfg.payments_live_provider_confirmed or not cfg.payments_live_provider_confirmation_required):
            mode = "LIVE"
        else:
            mode = "LIVE_DISABLED"
            warnings.append("ClickPesa points at a real host but the live flags are off: no collection")
        if not cfg.clickpesa_checksum_key:
            warnings.append("ClickPesa: CHECKSUM_KEY not set, so webhooks will be rejected")
    elif provider == "flutterwave":
        mode = "LIVE" if str(cfg.flutterwave_secret_key or "").startswith("FLWSECK-") else "TEST"
    if not str(cfg.public_base_url or "").strip():
        warnings.append("PUBLIC_BASE_URL is empty: receipt QR codes fall back to the server address")
    return {"provider": provider, "mode": mode, "real_money": mode == "LIVE", "warnings": warnings}


def cmd_preset_mock_payments(path: Path, *, lan_ip: str = "", port: int = 9100) -> int:
    """ClickPesa MOCK mode with fresh test credentials. Never touches real money."""
    existing = read_env(path)
    host = lan_ip or "127.0.0.1"
    updates = {
        env_key("payments_mobile_provider"): "clickpesa",
        env_key("clickpesa_base_url"): f"http://{host}:{port}/third-parties",
        env_key("clickpesa_live_enabled"): "false",
        env_key("payments_live_provider_confirmed"): "false",
    }
    for field, prefix in (("clickpesa_client_id", "mock-client-"), ("clickpesa_api_key", "mock-key-"),
                          ("clickpesa_checksum_key", "mock-checksum-")):
        current = existing.get(env_key(field), "")
        updates[env_key(field)] = current if current.startswith("mock-") else prefix + secrets.token_hex(12)
    write_env(path, updates)
    print(f"Mock payments configured in {path}")
    print(f"  provider: ClickPesa MOCK at http://{host}:{port}/third-parties (no real money)")
    print("  next: restart the services, then start the mock:")
    print("        python -m app.mock_services.clickpesa" + (" --host 0.0.0.0" if lan_ip else ""))
    print(f"  phone simulator: http://{host}:{port}/phone   faults: http://{host}:{port}/admin")
    return 0


def cmd_template() -> int:
    """A complete, commented .env template generated from the settings."""
    print("# Zirp settings. Every line is optional; the value shown is the default.")
    print("# Generated by: python -m app.cli env template\n")
    for field, info in sorted(field_names().items()):
        default = info.default if info.default is not None and not callable(info.default) else ""
        value = "" if is_secret(field) else str(default)
        print(f"# {env_key(field)}={_quote(value) if value else ''}")
    return 0


def restart_services() -> int:
    """Stop and start the SmartPark Windows services in dependency order."""
    if os.name != "nt":
        print("Restart the services with systemctl (e.g. sudo systemctl restart zirp-site).")
        return 0
    for name in SERVICES_STOP_ORDER:
        subprocess.run(["sc.exe", "stop", name], capture_output=True)
        _wait_service(name, "STOPPED")
    for name in reversed(SERVICES_STOP_ORDER):
        subprocess.run(["sc.exe", "start", name], capture_output=True)
        state = _wait_service(name, "RUNNING")
        print(f"{name}: {state}")
    return 0


def _wait_service(name: str, wanted: str, timeout: float = 60.0) -> str:
    import time

    deadline = time.monotonic() + timeout
    state = ""
    while time.monotonic() < deadline:
        out = subprocess.run(["sc.exe", "query", name], capture_output=True, text=True).stdout
        match = re.search(r"STATE\s*:\s*\d+\s+(\w+)", out)
        state = match.group(1) if match else "UNKNOWN"
        if state == wanted or state == "UNKNOWN":
            return state
        time.sleep(1)
    return state


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m app.cli env", description=__doc__.split("\n\n")[0])
    parser.add_argument("--env-file", help="default: .env in the Zirp install folder")
    parser.add_argument("--restart", action="store_true", help="restart SmartPark services afterwards (Windows)")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("list"); p.add_argument("--filter", default=""); p.add_argument("--changed", action="store_true")
    p = sub.add_parser("get"); p.add_argument("name"); p.add_argument("--reveal", action="store_true")
    p = sub.add_parser("set"); p.add_argument("assignments", nargs="+", metavar="NAME=VALUE")
    p.add_argument("--restart", action="store_true", dest="restart_after")
    p = sub.add_parser("unset"); p.add_argument("names", nargs="+")
    p.add_argument("--restart", action="store_true", dest="restart_after")
    sub.add_parser("check")
    p = sub.add_parser("preset"); p.add_argument("name", choices=["mock-payments"])
    p.add_argument("--lan-ip", default="", help="LAN IP so phones can reach the mock")
    p.add_argument("--port", type=int, default=9100)
    p.add_argument("--restart", action="store_true", dest="restart_after")
    sub.add_parser("template")
    sub.add_parser("restart", help="restart the SmartPark services so they read .env again")
    args = parser.parse_args(argv)
    path = env_file_path(args.env_file)
    try:
        if args.action == "list":
            code = cmd_list(path, filter_text=args.filter, changed=args.changed)
        elif args.action == "get":
            code = cmd_get(path, args.name, reveal=args.reveal)
        elif args.action == "set":
            code = cmd_set(path, args.assignments)
        elif args.action == "unset":
            code = cmd_unset(path, args.names)
        elif args.action == "check":
            code = cmd_check(path)
        elif args.action == "preset":
            code = cmd_preset_mock_payments(path, lan_ip=args.lan_ip, port=args.port)
        elif args.action == "restart":
            return restart_services()
        else:
            code = cmd_template()
    except (KeyError, ValueError) as exc:
        print(f"error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 2
    if code == 0 and (args.restart or getattr(args, "restart_after", False)) and args.action in {"set", "unset", "preset"}:
        restart_services()
    elif code == 0 and args.action in {"set", "unset", "preset"}:
        print("Restart the SmartPark services to apply (or re-run with --restart).")
    return code
