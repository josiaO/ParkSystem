"""Translation keys. UI may still ship English literals; new operator strings go through t()."""

from __future__ import annotations

from typing import Any

CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "lane.camera": "Camera",
        "lane.live_video": "Live Video",
        "lane.plate_recognition": "Plate Recognition",
        "lane.barrier": "Barrier",
        "status.online": "Online",
        "status.offline": "Offline",
        "status.ready": "Ready",
        "status.degraded": "Degraded",
        "status.unknown": "Unknown",
    },
    "sw": {
        "lane.camera": "Kamera",
        "lane.live_video": "Video ya moja kwa moja",
        "lane.plate_recognition": "Utambuzi wa namba",
        "lane.barrier": "Kizuizi",
        "status.online": "Imeunganishwa",
        "status.offline": "Imezimwa",
        "status.ready": "Tayari",
        "status.degraded": "Imepungua",
        "status.unknown": "Haijulikani",
    },
}


def t(key: str, *, language: str = "en", **kwargs: Any) -> str:
    lang = (language or "en").split("-", 1)[0].lower()
    catalog = CATALOGS.get(lang) or CATALOGS["en"]
    text = catalog.get(key) or CATALOGS["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
