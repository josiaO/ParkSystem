"""Replay a recorded lane clip through the real detector + OCR with three gates.

old         the removed ArrivalGate (git HEAD camera_framing.py): site zone
            0.06,0.18,0.94,0.92, 64 px capture width, fire-on-width
uncal       new CaptureGate, camera uncalibrated (whole picture, best of 3)
calibrated  new CaptureGate with a capture zone/line/size drawn for this clip

Dry run: no database, no sessions, no barrier. Prints JSON results.
"""
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, r"C:\SmartParkEdge")
os.environ.setdefault("SMARTPARK_HOME", r"C:\SmartParkEdge")
os.environ["SMARTPARK_DATABASE_URL"] = "sqlite://"

import cv2  # noqa: E402

from app.services.alpr import locate_plate_boxes, recognize_arrival_bytes  # noqa: E402
from app.services import capture_calibration as cc  # noqa: E402

CLIP = r"C:\SmartParkEdge\TestingData\Video Project.mp4"
SAMPLE_FPS = 5.0
OUT = sys.argv[1]

# The old gate, straight from the last commit.
old_src = subprocess.check_output(["git", "-C", r"C:\SmartParkEdge", "show", "HEAD:app/services/camera_framing.py"]).decode()
old_path = os.path.join(os.path.dirname(OUT), "old_camera_framing.py")
open(old_path, "w", encoding="utf-8").write(old_src)
spec = importlib.util.spec_from_file_location("old_camera_framing", old_path)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

OLD_ROI = "0.06,0.18,0.94,0.92"
CALIBRATION = cc.validate({
    "enabled": True,
    # lane approach seen by this camera: right half, lower part of the picture
    "zone": [[0.42, 0.55], [1.0, 0.55], [1.0, 1.0], [0.42, 1.0]],
    "trigger_line": {"y": 0.62, "side": "below"},
    "min_plate_width_px": 110, "min_plate_height_px": 28,
    "min_detection_confidence": 0.4, "min_sharpness": 80,
    "min_brightness": 35, "max_brightness": 235, "max_clipped_fraction": 0.5,
    "candidate_frames": 3, "candidate_seconds": 0.8,
})
UNCAL = cc.validate({})


def frames():
    cap = cv2.VideoCapture(CLIP)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(fps / SAMPLE_FPS)))
    index = 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        if index % step == 0:
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
            yield index / fps, buf.tobytes()
        index += 1


def ocr(jpeg, boxes):
    started = time.perf_counter()
    result = recognize_arrival_bytes(jpeg, camera_label="replay", detect_roi="off", detect_zoom=1.0,
                                     save_evidence=False, detected_boxes=boxes)
    best = (result or {}).get("best") or {}
    return str(best.get("plate_normalized") or best.get("plate") or ""), float(best.get("confidence") or 0), \
        round((time.perf_counter() - started) * 1000, 1)


def run():
    old_gate = old.ArrivalGate(min_plate_width_px=64, fire_on_width=True)
    gates = {"uncal": cc.CaptureGate(), "calibrated": cc.CaptureGate()}
    gates["uncal"].configure(UNCAL)
    gates["calibrated"].configure(CALIBRATION)
    reads = {"old": [], "uncal": [], "calibrated": []}
    first_seen = {"old": None, "uncal": None, "calibrated": None}
    detector_ms = []
    for t, jpeg in frames():
        started = time.perf_counter()
        boxes, located = locate_plate_boxes(jpeg, detect_roi="off", detect_zoom=1.0)
        detector_ms.append((time.perf_counter() - started) * 1000)
        if not located.get("available"):
            print("detector unavailable", located, file=sys.stderr)
            return None
        # old gate: its own zone, then its own phase machine
        box = old.best_arrival_box(boxes, detect_roi=OLD_ROI)
        if box and first_seen["old"] is None:
            first_seen["old"] = t
        phase = old_gate.observe(box, t)
        if phase in {"absent", "departed"}:
            first_seen["old"] = None
        if phase == "ready":
            plate, conf, ms = ocr(jpeg, boxes)
            reads["old"].append({"t": t, "plate": plate, "conf": conf, "width": old._plate_width(box), "ocr_ms": ms,
                                 "since_seen_s": round(t - (first_seen["old"] or t), 2)})
            old_gate.note_ocr(published=bool(plate))
        for name, gate in gates.items():
            config = UNCAL if name == "uncal" else CALIBRATION
            candidates = cc.evaluate_frame(jpeg, boxes, config)
            if candidates and first_seen[name] is None:
                first_seen[name] = t
            phase = gate.observe(candidates, boxes, jpeg, t)
            if phase == "absent":
                first_seen[name] = None
            if phase == "ready":
                sel = gate.selected
                plate, conf, ms = ocr(sel.jpeg, sel.boxes)
                reads[name].append({"t": t, "plate": plate, "conf": conf, "width": round(sel.candidate.width_px, 1),
                                    "frames_considered": sel.frames_considered, "ocr_ms": ms,
                                    "since_seen_s": round(t - (first_seen[name] or t), 2)})
                gate.note_ocr(published=bool(plate))
    summary = {}
    for name, rows in reads.items():
        plates = [r for r in rows if r["plate"]]
        summary[name] = {
            "ocr_calls": len(rows),
            "reads_with_text": len(plates),
            "distinct_plates": len({r["plate"] for r in plates}),
            "median_plate_width_px": statistics.median([r["width"] for r in rows]) if rows else None,
            "mean_ocr_confidence": round(statistics.mean([r["conf"] for r in plates]), 3) if plates else None,
            "median_seen_to_read_s": statistics.median([r["since_seen_s"] for r in rows]) if rows else None,
            "median_ocr_ms": statistics.median([r["ocr_ms"] for r in rows]) if rows else None,
        }
    body = {"clip": CLIP, "sample_fps": SAMPLE_FPS, "median_detector_ms": round(statistics.median(detector_ms), 1),
            "summary": summary, "reads": reads}
    json.dump(body, open(OUT, "w"), indent=1)
    print(json.dumps(body["summary"], indent=1), "detector_ms", body["median_detector_ms"])


run()
