# Streaming and ALPR acceptance checklist

- [ ] `docs/engineering/streaming-audit.md` reviewed by the site owner.
- [ ] `docs/engineering/streaming-baseline.md` updated with the actual Windows
      build and raw measurements.
- [ ] Every enabled camera has exactly one declared acquisition owner.
- [ ] QY/HVX host uses the matched 32-bit DLL family and remains callback-safe.
- [ ] Generic RTSP/ONVIF cameras use the configured MediaMTX path without a
      competing direct reader.
- [ ] LIVE/DETECT queues remain bounded during slow display and slow inference.
- [ ] Reconnect changes the media generation and no old frame/result is shown.
- [ ] Vehicle departure clears the current plate without deleting history.
- [ ] Native/software duplicate events produce one capture and one session.
- [ ] Replayed event IDs and transaction retries produce no second gate command.
- [ ] Camera, decoder, stale-frame, worker, model, outbox, and Site Server
      health states are distinguishable in diagnostics.
- [ ] Day and night labeled replay results include precision, recall,
      missed-vehicle rate, recognition latency, and duplicate-session rate.
- [ ] All installed cameras pass simultaneous daylight and night field tests.
- [ ] Recovery from an ordinary network interruption is measured and recorded.
- [ ] A 24-hour soak is complete, with no unbounded queue, duplicate session,
      orphan decoder, or unrecovered lane.
- [ ] Rollback flags and database/outbox backup procedure have been rehearsed.

Until the unchecked hardware and soak items are complete, the software should
be described as instrumented and regression-tested, not field-accepted.
