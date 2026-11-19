"""Per-car critical path from live latency traces (read-only, stdlib only).

Splits camera event -> parking decision into the segments that decide where
the access-decision latency actually goes:

    host callback -> ingested      event drain + event JPEG/crop fetch
    ingested -> capture_saved      ALPR + evidence (encode, file write, INSERT)
    capture_saved -> returned      access decision (lookups, policy, commits)

Usage::

    python tools/critical_path_report.py C:\\ProgramData\\SmartParkEdge\\logs [--since EPOCH_SECONDS]

``--since`` keeps only records written after that time (for example a deploy).

Joins host ``host.event.callback`` and Site Service ``recognition.native_event``
by ``capture_token`` and the ``lane.*`` stages by ``visit_id``. All arithmetic
uses ``perf_ns``, which processes on one PC share.
"""

from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict

LANE_STAGES = {
    "lane.capture_saved",
    "lane.parking_controller_entered",
    "lane.parking_controller_returned",
}


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))], 1)


def collect(folder: str, since: float = 0.0) -> dict[str, list[float]]:
    callbacks: dict[str, int] = {}
    ingested: dict[str, tuple[int, str]] = {}
    by_visit: dict[str, list[tuple[int, str]]] = defaultdict(list)
    segments: dict[str, list[float]] = defaultdict(list)
    for path in sorted(glob.glob(f"{folder}/latency-trace-*.jsonl*")):
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if ('"host.event.callback"' not in line and '"recognition.native_event"' not in line
                        and '"lane.' not in line and '"capture.pre_decision"' not in line):
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                stage, perf = record.get("stage"), record.get("perf_ns")
                if perf is None or float(record.get("ts") or 0) < since:
                    continue
                if stage == "host.event.callback" and record.get("capture_token"):
                    callbacks[record["capture_token"]] = perf
                elif stage == "recognition.native_event" and record.get("capture_token"):
                    ingested[record["capture_token"]] = (perf, str(record.get("visit_id") or ""))
                elif stage in LANE_STAGES and record.get("visit_id"):
                    by_visit[record["visit_id"]].append((perf, stage))
                elif stage == "capture.pre_decision":
                    label = "photos after decision" if record.get("evidence_deferred") else "photos before decision"
                    for key in ("prefetch_ms", "persist_ms", "lookups_ms", "total_ms"):
                        if isinstance(record.get(key), (int, float)):
                            segments[f"  capture save: {key} ({label})"].append(float(record[key]))

    for token, (at_ingest, visit) in ingested.items():
        if token not in callbacks or not visit:
            continue
        later = sorted(item for item in by_visit.get(visit, []) if item[0] >= at_ingest)
        saved = next((p for p, s in later if s == "lane.capture_saved"), None)
        if saved is None or saved - at_ingest > 30e9:
            continue
        returned = next((p for p, s in later if s == "lane.parking_controller_returned" and p >= saved), None)
        segments["event -> ingested (drain + image fetch)"].append((at_ingest - callbacks[token]) / 1e6)
        segments["ingested -> capture_saved (ALPR + evidence)"].append((saved - at_ingest) / 1e6)
        if returned is not None:
            segments["capture_saved -> decision (access engine)"].append((returned - saved) / 1e6)
            segments["END TO END event -> decision"].append((returned - callbacks[token]) / 1e6)
    return segments


def main(argv: list[str]) -> int:
    args = list(argv[1:])
    since = 0.0
    if "--since" in args:
        at = args.index("--since")
        since = float(args[at + 1])
        del args[at:at + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    segments = collect(args[0], since)
    print(f"{'segment (ms)':48s} {'n':>6s} {'p50':>8s} {'p95':>8s} {'p99':>8s} {'max':>9s}")
    for name, values in segments.items():
        print(f"{name:48s} {len(values):6d} {_pct(values, .5):8} {_pct(values, .95):8} {_pct(values, .99):8} {round(max(values), 1):9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
