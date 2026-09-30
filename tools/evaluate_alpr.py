"""Evaluate fixed ALPR labels against live inference or saved predictions.

Run from the repository root with ``python -m tools.evaluate_alpr --help``.
No training, label changes, or country corrections are performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Duplicate sample IDs in {path}")
    return rows


def edit_distance(left: str, right: str) -> int:
    costs = list(range(len(right) + 1))
    for index, char in enumerate(left, 1):
        previous, costs = costs, [index]
        for other, candidate in enumerate(right, 1):
            costs.append(min(costs[-1] + 1, previous[other] + 1, previous[other - 1] + (char != candidate)))
    return costs[-1]


def overlap(left: dict, right: dict) -> float:
    intersection = max(0, min(left["x2"], right["x2"]) - max(left["x1"], right["x1"])) * max(0, min(left["y2"], right["y2"]) - max(left["y1"], right["y1"]))
    area_left = max(0, left["x2"] - left["x1"]) * max(0, left["y2"] - left["y1"])
    area_right = max(0, right["x2"] - right["x1"]) * max(0, right["y2"] - right["y1"])
    union = area_left + area_right - intersection
    return intersection / union if union else 0.0


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _ratio(top: int, bottom: int) -> float | None:
    return top / bottom if bottom else None


def _metrics(labels: list[dict], predictions: dict[str, dict], iou_threshold: float) -> dict[str, Any]:
    positives = exact = characters = errors = box_labels = detected = negatives = false_positives = 0
    gate_negatives = false_acceptances = 0
    latencies = []
    for label in labels:
        prediction = predictions[label["id"]]
        plate = label.get("plate") or ""
        candidate = prediction.get("plate") or ""
        boxes = prediction.get("boxes") or []
        if plate:
            positives += 1
            exact += int(plate == candidate)
            characters += len(plate)
            errors += edit_distance(plate, candidate)
            if label.get("bbox"):
                box_labels += 1
                detected += int(any(overlap(label["bbox"], box) >= iou_threshold for box in boxes))
        else:
            negatives += 1
            false_positives += int(bool(candidate or boxes))
        # Gate acceptance is supplied by the real decision pipeline, never inferred
        # from OCR confidence. Unlabelled or missing decisions are excluded.
        if label.get("gate_allowed") is False and isinstance(prediction.get("accepted"), bool):
            gate_negatives += 1
            false_acceptances += int(prediction["accepted"])
        latency = prediction.get("latency_ms")
        if latency is not None:
            latency = float(latency)
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("Inference latency must be finite and non-negative")
            latencies.append(latency)
    return {
        "samples": len(labels), "positive_samples": positives, "negative_samples": negatives,
        "plate_exact_match_accuracy": _ratio(exact, positives),
        "character_accuracy": max(0.0, 1 - errors / characters) if characters else None,
        "character_edit_errors": errors, "ground_truth_characters": characters,
        "detection_recall": _ratio(detected, box_labels), "box_labelled_samples": box_labels,
        "false_positive_rate": _ratio(false_positives, negatives),
        "false_acceptance_rate": _ratio(false_acceptances, gate_negatives),
        "gate_negative_decisions": gate_negatives,
        "latency_ms": {"count": len(latencies), "mean": statistics.mean(latencies) if latencies else None,
                       "p50": percentile(latencies, .5), "p95": percentile(latencies, .95)},
    }


def evaluate(labels: list[dict], results: list[dict], *, iou_threshold: float = .5) -> dict:
    if not 0 < iou_threshold <= 1:
        raise ValueError("IoU threshold must be in (0, 1]")
    ids = [row["id"] for row in labels]
    predicted_ids = [row["id"] for row in results]
    if len(ids) != len(set(ids)) or len(predicted_ids) != len(set(predicted_ids)):
        raise ValueError("Duplicate sample IDs")
    if set(ids) != set(predicted_ids):
        raise ValueError("Predictions must cover every label exactly once; unknown IDs are rejected")
    predictions = {row["id"]: row for row in results}
    breakdown = {}
    for field in ("camera_id", "condition", "country", "profile"):
        groups: dict[str, list[dict]] = {}
        for label in labels:
            groups.setdefault(str(label.get(field) or "unknown"), []).append(label)
        breakdown[field] = {group: _metrics(rows, predictions, iou_threshold) for group, rows in sorted(groups.items())}
    return {"overall": _metrics(labels, predictions, iou_threshold), "by": breakdown, "iou_threshold": iou_threshold}


def infer(labels: list[dict], base: Path) -> list[dict]:
    from app.infrastructure.recognition.engines import recognize_frame

    results = []
    for label in labels:
        path = base / label["image"]
        result = recognize_frame(path.read_bytes(), camera_label=f"evaluation-{label['id']}")
        if not result.get("ok"):
            raise RuntimeError(f"Inference failed for sample {label['id']}; evaluation aborted")
        best = result.get("best") or {}
        results.append({"id": label["id"], "plate": best.get("plate_normalized") or "",
                        "boxes": [hit["bbox"] for hit in result.get("plates", []) if hit.get("bbox")],
                        "latency_ms": result.get("latency_ms")})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--predictions", type=Path, help="Saved JSONL predictions; omit to run FastALPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iou-threshold", type=float, default=.5)
    args = parser.parse_args()
    checksum = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    lock = args.manifest.with_suffix(args.manifest.suffix + ".sha256")
    if not lock.is_file() or lock.read_text().strip().split()[0] != checksum:
        parser.error("Manifest checksum missing or changed; use a reviewed, frozen validation dataset")
    labels = read_rows(args.manifest)
    if not labels:
        parser.error("The validation manifest is empty")
    if args.output and (args.output.resolve() == args.manifest.resolve() or args.output.resolve() == lock.resolve()):
        parser.error("Output must not overwrite validation labels or their checksum")
    results = read_rows(args.predictions) if args.predictions else infer(labels, args.manifest.parent)
    report = evaluate(labels, results, iou_threshold=args.iou_threshold)
    report["manifest_sha256"] = checksum
    report["prediction_source"] = "saved" if args.predictions else "fastalpr"
    report["dataset_kind"] = sorted({str(row.get("dataset_kind") or "unspecified") for row in labels})
    body = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(body + "\n", encoding="utf-8")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
