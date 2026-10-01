"""Multi-frame FastALPR consensus using DETECT-buffer reads.

Does not own JPEG storage — callers pass plates already OCR'd from
`LatestFrameBuffer.recent()` (the DETECT role buffer).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

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


@dataclass
class Reading:
    plate: str
    confidence: float
    at: float


@dataclass
class TrackDecision:
    publish: bool
    plate: str = ""
    confidence: float = 0.0
    reads: int = 0
    agreeing: int = 0
    share: float = 0.0
    candidates: dict = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "publish": self.publish,
            "plate": self.plate,
            "confidence": round(self.confidence, 4),
            "reads": self.reads,
            "agreeing": self.agreeing,
            "share": round(self.share, 4),
            "candidates": {k: round(v, 4) for k, v in self.candidates.items()},
            "reason": self.reason,
        }


@dataclass
class ConsensusTrack:
    """Similarity-weighted, confidence-weighted temporal consensus for one lane.

    Reads within ``window_seconds`` of each other belong to one *visit*. Each
    read votes for every candidate it resembles (``plate_similarity`` at or above
    ``similarity``), weighted by its OCR confidence and similarity, so a single
    confused character (``T285DOP`` vs ``T285DQP``) supports the majority text
    instead of splitting the vote. A plate is published once per visit when at
    least ``min_reads`` reads exist, the winner has ``min_agreeing`` identical
    reads and holds ``min_share`` of the weight; it is not re-published while
    continuously visible or within ``hold_seconds`` of the last publication.
    """

    window_seconds: float = 2.0
    hold_seconds: float = 20.0
    min_reads: int = 2
    min_agreeing: int = 2
    similarity: float = 0.7
    min_share: float = 0.6
    max_reads: int = 12
    readings: list = field(default_factory=list)
    published_plate: str = ""
    published_at: float = 0.0
    published_visit: float = -1.0
    visit_started_at: float = -1.0
    last_read_at: float | None = None
    # Compatibility fields read by older callers/tests.
    last_plate: str = ""
    streak: int = 0

    def _new_visit(self, now: float) -> None:
        self.readings.clear()
        self.visit_started_at = now
        self.streak = 0

    def observe(self, plate: str, now: float, *, confidence: float = 1.0) -> TrackDecision:
        from app.core.plate import plate_similarity

        plate = normalize_plate(plate)
        if self.last_read_at is None or now - self.last_read_at > self.window_seconds or now < self.last_read_at:
            self._new_visit(now)
        self.last_read_at = now
        if not plate:
            self.last_plate = ""
            self.streak = 0
            return TrackDecision(False, reason="empty read")
        self.streak = self.streak + 1 if plate == self.last_plate else 1
        self.last_plate = plate
        self.readings.append(Reading(plate, max(0.0, min(1.0, float(confidence or 0.0))), now))
        if len(self.readings) > self.max_reads:
            del self.readings[: len(self.readings) - self.max_reads]

        total = sum(r.confidence for r in self.readings) or 1e-9
        candidates: dict[str, float] = {}
        for candidate in {r.plate for r in self.readings}:
            score = 0.0
            for r in self.readings:
                if r.plate == candidate:
                    score += r.confidence
                else:
                    sim = plate_similarity(candidate, r.plate)
                    if sim >= self.similarity:
                        score += r.confidence * sim
            candidates[candidate] = score
        winner = max(candidates, key=lambda c: (candidates[c], sum(1 for r in self.readings if r.plate == c)))
        exact = [r for r in self.readings if r.plate == winner]
        share = min(1.0, candidates[winner] / total)
        confidence = sum(r.confidence for r in exact) / max(1, len(exact))
        decision = TrackDecision(
            False, winner, confidence, reads=len(self.readings), agreeing=len(exact), share=share, candidates=candidates,
        )
        if len(self.readings) < self.min_reads or len(exact) < self.min_agreeing:
            # Similar reads raise the winner's share but do not replace an exact
            # agreeing read; two identical texts are still required.
            decision.reason = "waiting for agreeing read"
            return decision
        if share < self.min_share:
            decision.reason = f"no consensus (share {share:.2f})"
            return decision
        if winner == self.published_plate:
            if self.published_visit == self.visit_started_at:
                decision.reason = "already published this visit"
                return decision
            if now - self.published_at < self.hold_seconds:
                decision.reason = "within hold window"
                return decision
        self.published_plate = winner
        self.published_at = now
        self.published_visit = self.visit_started_at
        decision.publish = True
        decision.reason = "consensus"
        return decision

    def release(self) -> None:
        """Forget the last publication so the next agreeing read may retry."""
        self.published_plate = ""
        self.published_at = 0.0
        self.published_visit = -1.0


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
