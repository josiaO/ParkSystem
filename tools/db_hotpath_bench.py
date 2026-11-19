"""Read-only benchmark of the access-decision queries on the live database.

Runs only SELECTs (plus ``select txid_current()`` to time one durable
commit, which writes no rows). Never touches gates, sessions or settings.

Usage (kit Python, on the Site Server)::

    python64\\python.exe tools\\db_hotpath_bench.py

Prints per-query latency, queries per call, the durable-commit cost, the
measured traffic profile (sessions per day, peak plates per minute / 5 min,
per hour of day) and PostgreSQL connection use.
"""

from __future__ import annotations

import itertools
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database_config import apply_runtime_database_config  # noqa: E402
from app.deployment import load_deployment_config  # noqa: E402

apply_runtime_database_config(load_deployment_config().database)

from sqlalchemy import event, text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402

_count = {"n": 0}


@event.listens_for(engine, "before_cursor_execute")
def _counter(*_args, **_kwargs):
    _count["n"] += 1


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))], 2)


def bench(label: str, fn, n: int = 200) -> None:
    times, queries = [], []
    for _ in range(n):
        before = _count["n"]
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000)
        queries.append(_count["n"] - before)
    print(f"{label:44s} p50={_pct(times, .5):7.2f} p95={_pct(times, .95):7.2f} max={max(times):8.2f} ms  "
          f"queries/call={statistics.mean(queries):.1f}")


def main() -> int:
    from app.application.entry_lane import recent_lookalike_session
    from app.services.access import lookup_entitlement
    from app.services.captures import latest_for_camera
    from app.services.parking_sessions import active_for_plate

    with SessionLocal() as db:
        if db.bind.dialect.name != "postgresql":
            print("This benchmark is meant for the PostgreSQL site database.")
        plates = [r[0] for r in db.execute(text(
            "select plate from parking_sessions where plate <> '' order by id desc limit 200"))] or ["T000AAA"]
        cycle = itertools.cycle(plates)
        gate_id = db.execute(text("select id from gates order by id limit 1")).scalar()
        print("== access-decision queries ==")
        bench("round trip (select 1)", lambda: db.execute(text("select 1")).scalar())
        bench("lookup_entitlement (strict)", lambda: lookup_entitlement(db, next(cycle), site_id=1, strict=True))
        bench("active_for_plate", lambda: active_for_plate(db, next(cycle), site_id=1))
        bench("recent_lookalike_session", lambda: recent_lookalike_session(db, next(cycle), gate_id))
        bench("latest_for_camera", lambda: latest_for_camera(db, 1))
        db.rollback()

    with engine.connect() as conn:
        times = []
        for _ in range(200):
            started = time.perf_counter()
            conn.execute(text("select txid_current()"))
            conn.commit()
            times.append((time.perf_counter() - started) * 1000)
        print(f"{'durable commit (WAL flush)':44s} p50={_pct(times, .5):7.2f} p95={_pct(times, .95):7.2f} max={max(times):8.2f} ms")

    with SessionLocal() as db:
        rows = lambda sql: db.execute(text(sql)).all()  # noqa: E731
        print("\n== traffic ==")
        for day, count in rows("select created_at::date, count(*) from parking_sessions "
                               "where created_at > now() - interval '8 days' group by 1 order by 1"):
            print(f"sessions {day}: {count}")
        print("peak distinct plates / minute:", [(str(m), n) for m, n in rows(
            "select date_trunc('minute', created_at), count(distinct plate) from vehicle_captures "
            "where created_at > now() - interval '7 days' and plate <> '' group by 1 order by 2 desc limit 3")])
        print("peak distinct plates / 5 min:", [(str(m), n) for m, n in rows(
            "select to_timestamp(floor(extract(epoch from created_at) / 300) * 300), count(distinct plate) "
            "from vehicle_captures where created_at > now() - interval '7 days' and plate <> '' "
            "group by 1 order by 2 desc limit 3")])
        print("\n== database ==")
        print("connections:", rows("select application_name, state, count(*) from pg_stat_activity "
                                   "where datname = current_database() group by 1, 2 order by 3 desc"))
        print("synchronous_commit:", rows("show synchronous_commit")[0][0], " fsync:", rows("show fsync")[0][0])
        db.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
