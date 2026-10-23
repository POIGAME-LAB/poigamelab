#!/usr/bin/env python3
"""Generate lightweight WebP card images (assets/game-cards) from games.csv.

Aspect ratio is preserved (no crop) so CSS object-fit:cover crops exactly as it
does with the original. Run after adding/replacing a game image, then commit.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_WIDTH = 800
MAX_BYTES = 90 * 1024


def card_name(image_value: str) -> str:
    raw = str(image_value or "").split("?", 1)[0].strip()
    if not raw.startswith("assets/game-art/"):
        return ""
    value = Path(raw).name
    if Path(value).suffix.lower() not in RASTER_SUFFIXES:
        return ""
    while Path(value).suffix.lower() in RASTER_SUFFIXES:
        value = Path(value).stem
    return f"{value.lower()}.webp"


def save_card(source: Path, destination: Path) -> int:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for quality in (80, 74, 68, 62, 56):
        image.save(destination, format="WEBP", quality=quality, method=6)
        if destination.stat().st_size <= MAX_BYTES:
            break
    size = destination.stat().st_size
    if size > MAX_BYTES:
        raise RuntimeError(f"card_image_too_large:{destination.name}:{size}")
    return size


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="assets/game-cards")
    args = parser.parse_args(argv)
    output = (ROOT / args.output).resolve()
    seen: set[str] = set()
    total = 0
    with (ROOT / "games.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            image_value = str(row.get("image") or "").strip()
            name = card_name(image_value)
            if not name or name in seen:
                continue
            seen.add(name)
            source = ROOT / image_value.split("?", 1)[0]
            if not source.is_file() or source.is_symlink():
                raise FileNotFoundError(f"missing_source:{image_value}")
            size = save_card(source, output / name)
            total += size
            print(f"{name}\t{size} bytes\t<- {image_value}")
    print(f"{len(seen)} card images, {total} bytes total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
