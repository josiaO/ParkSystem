#!/usr/bin/env python3
"""Prepare the existing Zirp artwork for Windows/app icon surfaces.

This does not draw or generate a new logo.  It removes the white canvas from
the supplied artwork, keeps the original mark, and writes the existing ICO
targets as a transparent, tightly framed multi-size icon.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def _transparent_mark(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    rgb = image.convert("RGB")
    white = Image.new("RGB", image.size, (255, 255, 255))
    difference = ImageChops.difference(rgb, white).convert("L")

    # The supplied artwork is RGB with a white background. Preserve the
    # original colors while converting only the near-white canvas to alpha.
    alpha = difference.point(lambda value: 0 if value < 10 else min(255, value * 3))
    image.putalpha(alpha)
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError(f"logo artwork contains no visible mark: {source}")

    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    padding = max(8, int(max(width, height) * 0.08))
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    cropped = image.crop((left, top, right, bottom))

    side = max(cropped.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2), cropped)
    return canvas.resize((1024, 1024), Image.Resampling.LANCZOS)


def prepare(source: Path, outputs: list[Path]) -> None:
    icon = _transparent_mark(source)
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        icon.save(output, format="ICO", sizes=[(size, size) for size in ICON_SIZES])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, action="append", required=True)
    args = parser.parse_args()
    prepare(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
