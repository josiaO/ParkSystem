from __future__ import annotations

@dataclass
class PlateHit:
    plate_raw: str
    plate_normalized: str
    plate_confidence: float
    plate_crop_path: str | None = None
    bbox: dict | None = None
    detector_confidence: float = 0.0
    timings: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict:
        crop = self.plate_crop_path.replace("\\", "/") if self.plate_crop_path else None
        return {
            "plate": self.plate_normalized or self.plate_raw,
            "plate_raw": self.plate_raw,
            "plate_normalized": self.plate_normalized,
            "confidence": self.plate_confidence,
            "plate_crop_path": crop,
            "crop_url": f"/media/{crop}" if crop else None,
            "bbox": self.bbox,
            "event_id": self.event_id,
            "detector_confidence": self.detector_confidence,
            "timings": self.timings,
        }

def bbox_dict(bbox) -> dict | None:
    if bbox is None:
        return None
    try:
        return {
            "x1": int(getattr(bbox, "x1")),
            "y1": int(getattr(bbox, "y1")),
            "x2": int(getattr(bbox, "x2")),
            "y2": int(getattr(bbox, "y2")),
        }
    except Exception:
        return None

def annotate_image(image_path: str, hits: list[PlateHit], dest_name: str | None = None) -> str | None:
    boxes = [hit for hit in hits if hit.bbox]
    if not boxes:
        return None
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        for hit in boxes:
            box = hit.bbox or {}
            xy = [box["x1"], box["y1"], box["x2"], box["y2"]]
            draw.rectangle(xy, outline="#22c55e", width=max(3, img.width // 400))
            label = f"{hit.plate_normalized} {hit.plate_confidence:.0%}"
            tx, ty = xy[0], max(0, xy[1] - 22)
            draw.rectangle([tx, ty, tx + 8 * len(label), ty + 20], fill="#166534")
            draw.text((tx + 4, ty + 2), label, fill="#ffffff")
        folder = settings.media_dir / "annotated"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (dest_name or f"{uuid.uuid4().hex}.jpg")
        img.save(dest, quality=85)
        return dest.relative_to(settings.media_dir).as_posix()
    except Exception:
        return None
