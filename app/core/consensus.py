"""Multi-frame FastALPR consensus using DETECT-buffer reads.

Does not own JPEG storage — callers pass plates already OCR'd from
`LatestFrameBuffer.recent()` (the DETECT role buffer).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.core.plate import normalize_plate

DEFAULT_AGREE = 2
DEFAULT_HIGH_CONF = 0.92
DEFAULT_WINDOW = 3


@dataclass
class ConsensusDecision:
    plate: str
    confidence: float
    accepted: bool
    reason: str
    agreeing: int = 0
    frames: int = 0

    def as_dict(self) -> dict:
        return {
            "plate": self.plate,
            "confidence": self.confidence,
            "accepted": self.accepted,
            "reason": self.reason,
            "agreeing": self.agreeing,
            "frames": self.frames,
        }


def resolve_local_reads(
    reads: list[tuple[str, float]] | None,
    *,
    agree_count: int = DEFAULT_AGREE,
    high_conf: float = DEFAULT_HIGH_CONF,
) -> ConsensusDecision:
    """Accept FastALPR only with two agreeing frames or one strict high-confidence read."""
    cleaned: list[tuple[str, float]] = []
    for raw, conf in reads or []:
        plate = normalize_plate(raw)
        if not plate:
            continue
        cleaned.append((plate, float(conf or 0)))
    frames = len(cleaned)
    if not cleaned:
        return ConsensusDecision("", 0.0, False, "no local reads", frames=0)

    best_plate, best_conf = max(cleaned, key=lambda item: item[1])
    if best_conf >= float(high_conf):
        agreeing = sum(1 for plate, _ in cleaned if plate == best_plate)
        return ConsensusDecision(
            best_plate, best_conf, True, "high-confidence single frame", agreeing=max(1, agreeing), frames=frames,
        )

    counts = Counter(plate for plate, _ in cleaned)
    plate, agreeing = counts.most_common(1)[0]
    conf = max(score for text, score in cleaned if text == plate)
    if agreeing >= int(agree_count or DEFAULT_AGREE):
        return ConsensusDecision(plate, conf, True, "multi-frame agreement", agreeing=agreeing, frames=frames)
    return ConsensusDecision(
        best_plate, best_conf, False, "no consensus", agreeing=agreeing, frames=frames,
    )


def detect_coverage(*, fps: float, dwell_seconds: float, min_frames: int = 2) -> dict:
    """Frame-interval vs time-in-view for DETECT OCR (typical entry ~1s plate dwell)."""
    rate = float(fps or 0)
    dwell = float(dwell_seconds or 0)
    interval_ms = (1000.0 / rate) if rate > 0 else None
    expected = int(rate * dwell) if rate > 0 and dwell > 0 else 0
    return {
        "fps": rate,
        "dwell_seconds": dwell,
        "interval_ms": round(interval_ms, 1) if interval_ms is not None else None,
        "expected_frames": expected,
        "enough_for_consensus": expected >= int(min_frames or 2),
    }
