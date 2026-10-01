# ALPR evaluation

Run the deterministic synthetic metrics smoke check:

```bash
.venv/bin/python -m tools.evaluate_alpr tests/fixtures/alpr/smoke.jsonl \
  --predictions tests/fixtures/alpr/smoke-predictions.jsonl --output /tmp/alpr-smoke.json
```

The bundled fixtures contain **labels and fabricated predictions, not camera
images**. Their metrics verify calculations and must not be presented as measured
model accuracy. No real validation images were supplied for this phase.

## Fixed validation data

Curate a reviewed JSONL manifest separately from training/tuning. Each row has a
unique `id`, an `image` path relative to the manifest, `plate` (exact normalized
ground truth, or null for no plate), optional `bbox` with pixel x1/y1/x2/y2,
`camera_id`, `condition` (`daylight`/`night`), and optional `country`/`profile`.
Set `dataset_kind` to describe real, synthetic, or other provenance. This first
harness supports one labelled plate per image; multi-vehicle scenes need separate
annotated crops. Preserve original images and labels in a restricted data store.

Freeze the manifest by recording its SHA-256 in `<manifest>.sha256`; review both
files together. The CLI refuses missing or mismatched checksums and records the
checksum in the report. It never edits labels and prevents report output from
overwriting the manifest/checksum. Keep image content frozen alongside labels.

Omit `--predictions` to run the configured local plate engine on every image.
Engine errors abort evaluation; they are never counted as successful reads.
Missing files abort evaluation. Models reuse the existing engine cache. Latency
is the engine's detector/OCR latency and includes cold loading on the first read;
it excludes report writing and image annotation. Record model versions, hardware,
settings and cold/warm status when comparing runs.

For saved results use one JSONL prediction per sample:

```json
{"id":"sample-1","plate":"ABC123","boxes":[{"x1":10,"y1":10,"x2":100,"y2":40}],"latency_ms":140,"accepted":false}
```

Unknown, duplicate and missing IDs are rejected.

## Metric definitions

- Exact match: correct plate text / plate-positive images. Comparisons are exact;
  the harness does not apply OCR substitutions or country normalization.
- Character accuracy: `max(0, 1 - total Levenshtein edit errors / labelled characters)`.
  A missed plate contributes deletion errors.
- Detection recall: bbox-labelled positive images with a predicted box at IoU
  >= 0.5 / bbox-labelled positives. The threshold is configurable. Without box
  labels this is unknown, not a text-based proxy.
- False positive rate: no-plate images with predicted text or boxes / no-plate images.
- False acceptance rate: accepted decisions / labelled gate-negative scenarios
  with recorded decisions. Add `gate_allowed=false` to those manifest rows.
  `accepted` must come from an actual access-decision test; OCR confidence is not
  a substitute. Direct inference cannot measure this metric and reports null.
- Latency: mean and linearly interpolated p50/p95 in milliseconds, with sample count.

Reports include denominators and breakdowns by camera, condition, country and
profile. Missing denominators/labels produce null rather than misleading zeroes.
The harness evaluates candidates; it never controls gates or changes parking data.
