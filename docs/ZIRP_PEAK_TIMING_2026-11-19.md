# Zirp peak timing re-measure — 2026-11-19

Read-only measurement on SERVER01 at 19:31 (+03:00). No files outside this report were changed, no services restarted, no gate pulsed.

- Tool: `tools/critical_path_report.py C:\ProgramData\SmartParkEdge\logs --since <epoch>` and `tools/db_hotpath_bench.py`, run with the kit Python.
- Window A: since 2026-11-19 08:55 +03:00 (epoch 1795067700), after the `capture.pre_decision` timing points went in. Runs to 19:31.
- Window B: since 2026-11-19 16:00 +03:00 (epoch 1795093200), the evening peak. The tool has no end bound, so this is 16:00–19:31.

## Cars covered

| Window | Cars (end to end) | Capture saves (photos after decision) | Capture saves (photos before decision) |
|---|---:|---:|---:|
| A (08:55 → now) | 3,566 | 3,649 | 69 |
| B (16:00 → now) | 981 | 953 | 22 |

Both main windows have enough cars for a conclusion. The "photos before decision" rows (69 and 22) are under ~100 and are too few to conclude anything from. They show that a small share of captures after the step 3 deploy still recorded `evidence_deferred = false`; this data does not say why.

## Window A — since 08:55

| segment (ms) | n | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| event → ingested (drain + image fetch) | 3,566 | 526.8 | 1,188.2 | 2,001.1 | 5,504.3 |
| ingested → capture_saved (ALPR + evidence) | 3,566 | 255.0 | 599.9 | 2,074.7 | 15,773.0 |
| capture_saved → decision (access engine) | 3,566 | 55.9 | 149.0 | 222.9 | 553.4 |
| **end to end event → decision** | 3,566 | **845.0** | **1,916.1** | 3,718.5 | 16,143.3 |

## Window B — peak, since 16:00

| segment (ms) | n | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| event → ingested (drain + image fetch) | 981 | 634.5 | 1,599.5 | 2,393.7 | 5,504.3 |
| ingested → capture_saved (ALPR + evidence) | 981 | 305.4 | 1,091.3 | 4,798.4 | 11,642.0 |
| capture_saved → decision (access engine) | 981 | 62.8 | 169.4 | 265.7 | 496.7 |
| **end to end event → decision** | 981 | **1,011.9** | **2,930.8** | 6,557.7 | 12,755.5 |

## Capture save split (`capture.pre_decision`)

Photos after decision (the step 3 path):

| field (ms) | A p50 | A p95 | B p50 | B p95 |
|---|---:|---:|---:|---:|
| prefetch_ms | 1.8 | 3.6 | 1.9 | 4.4 |
| persist_ms | 15.7 | 63.4 | 19.4 | 102.4 |
| lookups_ms | 6.6 | 18.5 | 7.6 | 24.7 |
| **total_ms** | **24.5** | **83.8** | **30.0** | **123.4** |

Photos before decision (n = 69 / 22; too few to conclude from):

| field (ms) | A p50 | A p95 | B p50 | B p95 |
|---|---:|---:|---:|---:|
| prefetch_ms | 1.8 | 4.6 | 2.3 | 6.5 |
| persist_ms | 7.7 | 46.4 | 11.1 | 52.0 |
| lookups_ms | 7.5 | 17.4 | 9.9 | 23.0 |
| total_ms | 17.5 | 66.8 | 24.1 | 75.9 |

## Database hot path (`db_hotpath_bench.py`, run 19:31)

| query | p50 ms | p95 ms | max ms | queries/call |
|---|---:|---:|---:|---:|
| round trip (select 1) | 0.26 | 0.78 | 1.52 | 1.0 |
| lookup_entitlement (strict) | 0.79 | 1.67 | 70.92 | 1.0 |
| active_for_plate | 0.93 | 2.45 | 8.80 | 1.0 |
| recent_lookalike_session | 1.80 | 3.77 | 4.63 | 1.0 |
| latest_for_camera | 0.96 | 2.04 | 13.12 | 1.0 |
| durable commit (WAL flush) | 0.63 | 1.12 | 3.43 | — |

- Connections: `smartpark-service` 1 active + 1 idle; pgAdmin 4 sessions: 4.
- `synchronous_commit = on`, `fsync = on`.
- Sessions per day: 11-12: 97, 11-15: 60, 11-16: 96, 11-17: 725, 11-18: 1,132, 11-19: 885 (so far).
- Peak distinct plates: 19 / minute (2026-11-18 18:22), 50 / 5 min (2026-11-18 18:20).

## Comparison with the baseline (before step 1, ~4,000 cars)

| segment | baseline p50 / p95 | A p50 / p95 | B (peak) p50 / p95 |
|---|---|---|---|
| event → ingested | 506 / 1,125 | 527 / 1,188 | 635 / 1,600 |
| ingested → capture_saved | 361 / 696 | 255 / 600 | 305 / 1,091 |
| capture_saved → decision | 22 / 77 | 56 / 149 | 63 / 169 |
| end to end | 910 / 1,900 | 845 / 1,916 | 1,012 / 2,931 |

After step 1 only (129 cars, mostly overnight) the decision segment was 41 / 145 ms.

The baseline covers all hours, not just a peak, so window B is compared against an all-hours baseline.

## Conclusions

**(i) Photo work vs plate reading in "ingested → capture_saved".** With photos written after the decision, the whole capture save (prefetch + persist + lookups) is 24.5 ms at p50 and 83.8 ms at p95 in window A. That is about 10% of the 255 ms p50 segment and about 14% of the 600 ms p95. At the peak it is 30 / 123 ms against 305 / 1,091 ms (about 10% / 11%). This assumes the capture save sits inside the segment, which is how the stages are ordered. The remaining ~230 ms p50 (A) and ~275 ms p50 (B) is plate reading and the earlier steps of the segment, not photo writing. The segment's p50 fell from 361 to 255 ms all day. At the peak its p95 (1,091 ms) is worse than the baseline (696 ms), and the capture save accounts for only ~123 ms of that, so most of the peak tail comes from outside the capture save.

**(ii) Step 1 decision time vs the 200 ms p95 target.** The decision segment is p95 149 ms all day and **p95 169 ms at the peak: under the 200 ms target**. Compared with the baseline (22 / 77 ms) that is about +34–41 ms at p50 and +72–92 ms at p95. The p99 is over 200 ms (223 ms in A, 266 ms at the peak), so about 1–2% of peak cars wait more than 200 ms in this segment. DB queries (≤ 3.8 ms p95 each) and the durable commit (1.1 ms p95) were fast when measured at 19:31. That reading is a single sample after the peak, not during it.

**End to end.** All day it is roughly unchanged from the baseline (845 / 1,916 vs 910 / 1,900 ms). At the peak it is slower (1,012 / 2,931 ms), mainly because event → ingested (p95 1,600 ms) and ingested → capture_saved (p95 1,091 ms) grow under load, not because of the decision segment.
