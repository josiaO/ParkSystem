# RECOGNITION Module

Plate reading is a separate engine. The camera snaps the JPEG. The engine returns the plate. Parking consumes the normalized event.

The known engine is **FastALPR** (`fastalpr-1`). It replaces ParkWatch SimpleLPR: every presence JPEG is read in software, with Tanzania as the country profile.

Contract, retrain steps, and how to register another library: [../PLATE-ENGINE.md](../PLATE-ENGINE.md).

Pipeline details: [../FASTALPR-PIPELINE.md](../FASTALPR-PIPELINE.md).

Code:

- `app/infrastructure/recognition/engines/` — engine contract, FastALPR, registry, training packs
- `app/services/alpr.py` — detect, crop, OCR
- `app/services/ocr_policy.py` — `FASTALPR_ONLY` by default
- Desktop page **Plate Engine** (Windows and Linux)
