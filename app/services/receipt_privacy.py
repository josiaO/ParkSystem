"""What the public receipt page may show to whoever holds the receipt link.

The receipt token is a 256-bit bearer secret, but receipts are paper: they are
dropped, photographed and passed on. The entry photo can show the driver,
passengers and other vehicles, so it is not public by default.

``SMARTPARK_PUBLIC_RECEIPT_PHOTO``:

* ``off`` (default): no entry photo or plate crop on the public page.
* ``blurred``: a heavily blurred entry photo (vehicle shape and colour only),
  no plate crop.
* ``full``: the original photo and plate crop (explicit opt-in).

Signed-in operators (kiosk, desktop) always get the original images.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from app.config import settings

PHOTO_OFF = "off"
PHOTO_BLURRED = "blurred"
PHOTO_FULL = "full"
_MODES = {PHOTO_OFF, PHOTO_BLURRED, PHOTO_FULL}
HIDDEN_NOTE = "The entry photo is not shown on the public receipt. If the plate is wrong, ask the parking team."


def public_photo_mode() -> str:
    from app.services import runtime_settings

    mode = str(runtime_settings.get("public_receipt_photo") or PHOTO_OFF).strip().lower()
    return mode if mode in _MODES else PHOTO_OFF


def driver_image_fields(body: dict) -> dict:
    """Restrict a presentation body for an anonymous receipt-link holder."""
    mode = public_photo_mode()
    if mode == PHOTO_FULL:
        return body
    body = dict(body)
    body["crop_url"] = None
    if mode == PHOTO_OFF:
        body["snapshot_url"] = None
        body["image_note"] = HIDDEN_NOTE
    return body


def public_image_allowed(kind: str) -> bool:
    mode = public_photo_mode()
    if mode == PHOTO_FULL:
        return True
    return mode == PHOTO_BLURRED and kind == "snapshot"


def blurred_jpeg(path: Path) -> bytes:
    """Strong blur scaled to the image, so faces and other plates are unreadable."""
    from PIL import Image, ImageFilter

    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((640, 640))
        radius = max(4, max(image.size) // 20)
        out = BytesIO()
        image.filter(ImageFilter.GaussianBlur(radius)).save(out, "JPEG", quality=70)
    return out.getvalue()
