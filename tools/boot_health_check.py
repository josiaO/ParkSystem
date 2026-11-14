"""Post-boot recovery check (Phase 3.4). Standard library only.

Run at boot (as SYSTEM, before anyone signs in) by tools/Test-RebootRecovery.ps1.
Within --timeout-minutes it waits for:

* every installed SmartPark Windows service to be RUNNING;
* GET /health/live -> 200 and GET /health/ready -> 200 on the Site Service;
* the HVX SDK host /info answering, if it is installed as a service.

It writes a JSON report and exits 0 on PASS, 1 on FAIL. It changes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SERVICES = ("SmartParkSiteService", "SmartParkMediaService", "SmartParkRecognitionWorker", "SmartParkHvxHost")


def http_status(url: str, timeout: float = 3.0) -> int:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0


def service_states() -> dict[str, str | None]:
    """RUNNING/STOPPED/... per service; None when not installed (or not Windows)."""
    states: dict[str, str | None] = {}
    for name in SERVICES:
        state = None
        if os.name == "nt":
            try:
                out = subprocess.run(["sc.exe", "query", name], capture_output=True, text=True, timeout=5)
                if out.returncode == 0:
                    for line in out.stdout.splitlines():
                        if "STATE" in line and ":" in line:
                            parts = line.split(":", 1)[1].split()
                            state = parts[1].upper() if len(parts) > 1 else None
            except (OSError, subprocess.TimeoutExpired):
                state = None
        states[name] = state
    return states


def evaluate(states: dict[str, str | None], live: int, ready: int, hvx: int | None) -> dict:
    installed = {name: state for name, state in states.items() if state is not None}
    checks = {
        "services_running": bool(installed) and all(state == "RUNNING" for state in installed.values()),
        "health_live": live == 200,
        "health_ready": ready == 200,
    }
    if states.get("SmartParkHvxHost") is not None:
        checks["hvx_host"] = hvx == 200
    return {"ok": all(checks.values()), "checks": checks, "services": states,
            "http": {"live": live, "ready": ready, "hvx_info": hvx}}


def run(
    *,
    base_url: str,
    timeout_seconds: float,
    poll_seconds: float = 5.0,
    get_status: Callable[[str], int] = http_status,
    get_services: Callable[[], dict[str, str | None]] = service_states,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    started = clock()
    boot_reference = datetime.now(timezone.utc).isoformat()
    result: dict = {}
    while True:
        states = get_services()
        live = get_status(f"{base_url}/health/live")
        ready = get_status(f"{base_url}/health/ready")
        hvx = get_status("http://127.0.0.1:8765/info") if states.get("SmartParkHvxHost") is not None else None
        result = evaluate(states, live, ready, hvx)
        elapsed = clock() - started
        if result["ok"] or elapsed >= timeout_seconds:
            result.update(
                seconds_to_green=round(elapsed, 1) if result["ok"] else None,
                timeout_seconds=timeout_seconds,
                checked_at=datetime.now(timezone.utc).isoformat(),
                started_at=boot_reference,
                verdict="PASS" if result["ok"] else "FAIL",
            )
            return result
        sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8760")
    parser.add_argument("--timeout-minutes", type=float, default=5.0)
    parser.add_argument("--report", default="")
    args = parser.parse_args(argv)
    result = run(base_url=args.url.rstrip("/"), timeout_seconds=args.timeout_minutes * 60)
    text = json.dumps(result, indent=2)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
