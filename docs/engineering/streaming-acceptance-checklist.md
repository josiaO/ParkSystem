# Streaming and ALPR acceptance checklist

- [x] `docs/engineering/streaming-audit.md` reviewed against the current
      worktree.
- [x] `docs/engineering/streaming-baseline.md` updated with the current
      software build evidence; Windows raw measurements remain a field gate.
- [x] Every enabled camera has exactly one declared acquisition owner.
- [x] QY/HVX host uses the matched 32-bit DLL family and remains callback-safe.
- [x] Generic RTSP/ONVIF cameras use the configured MediaMTX path without a
      competing direct reader in production.
- [x] LIVE/DETECT queues remain bounded during slow display and slow inference.
- [x] Reconnect changes the media generation and no old frame/result is shown.
- [x] Vehicle departure clears the current plate without deleting history.
- [x] Native/software duplicate events produce one capture and one session.
- [x] Replayed event IDs and transaction retries produce no second gate command.
- [x] Camera, decoder, stale-frame, worker, model, outbox, and Site Server
      health states are distinguishable in diagnostics.
- [ ] MANUAL WINDOWS/HARDWARE: day and night labeled replay results include
      precision, recall, missed-vehicle rate, recognition latency, and
      duplicate-session rate.
- [ ] MANUAL WINDOWS/HARDWARE: all installed cameras pass simultaneous
      daylight and night field tests.
- [ ] MANUAL WINDOWS/HARDWARE: recovery from an ordinary network interruption
      is measured and recorded.
- [ ] MANUAL WINDOWS/HARDWARE: a 24-hour soak is complete, with no unbounded
      queue, duplicate session, orphan decoder, or unrecovered lane.
- [ ] MANUAL WINDOWS/HARDWARE: rollback flags and database/outbox backup
      procedure have been rehearsed.

The software implementation and automated verification are complete for this
worktree. Until the unchecked Windows/hardware items are complete, describe the
system as instrumented and regression-tested, not field-accepted.
