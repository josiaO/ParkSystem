"""Named FFmpeg ingest profiles. Do not apply random low-latency flags globally."""

from __future__ import annotations

from app.domain.media import FFMPEG_PROFILES, RTSP_TRANSPORTS

DEFAULT_PROFILE = "LOW_LATENCY_LAN"
FALLBACK_PROFILE = "COMPATIBLE"

_PROFILES: dict[str, dict[str, str]] = {
    "COMPATIBLE": {
        "rtsp_transport": "tcp",
        "fflags": "+genpts",
        "probesize": "5000000",
        "analyzeduration": "5000000",
        "max_delay": "500000",
    },
    "LOW_LATENCY_LAN": {
        "rtsp_transport": "tcp",
        "fflags": "nobuffer+discardcorrupt",
        "flags": "low_delay",
        "probesize": "32",
        "analyzeduration": "0",
        "max_delay": "100000",
        "avioflags": "direct",
    },
    "LOSSY_NETWORK": {
        "rtsp_transport": "tcp",
        "fflags": "nobuffer+discardcorrupt",
        "probesize": "1000000",
        "analyzeduration": "1000000",
        "max_delay": "1000000",
    },
    "VENDOR_SPECIAL": {
        "rtsp_transport": "tcp",
        "fflags": "+genpts",
        "probesize": "2000000",
        "analyzeduration": "2000000",
        "max_delay": "500000",
    },
}


def normalize_profile(name: str | None) -> str:
    key = str(name or DEFAULT_PROFILE).strip().upper() or DEFAULT_PROFILE
    return key if key in _PROFILES else DEFAULT_PROFILE


def normalize_transport(name: str | None) -> str:
    key = str(name or "TCP").strip().upper() or "TCP"
    if key in RTSP_TRANSPORTS:
        return key
    return "TCP"


def transport_flag(name: str | None) -> str:
    key = normalize_transport(name)
    if key == "UDP":
        return "udp"
    return "tcp"


def profile_args(name: str | None, *, transport: str | None = None) -> list[str]:
    spec = dict(_PROFILES[normalize_profile(name)])
    if transport:
        spec["rtsp_transport"] = transport_flag(transport)
    args: list[str] = []
    for key, value in spec.items():
        args.extend([f"-{key}", value])
    return args


def fallback_profile(name: str | None) -> str:
    current = normalize_profile(name)
    if current == FALLBACK_PROFILE:
        return FALLBACK_PROFILE
    return FALLBACK_PROFILE


def list_profiles() -> list[dict]:
    return [
        {"id": key, "args": profile_args(key), "fallback": fallback_profile(key) if key != FALLBACK_PROFILE else None}
        for key in FFMPEG_PROFILES
    ]
