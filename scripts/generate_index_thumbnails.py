#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg"}
THUMB_SIZE = (246, 246)
MAX_BYTES = 80 * 1024


def _strip_raster_suffixes(filename: str) -> str:
    value = filename
    while Path(value).suffix.lower() in RASTER_SUFFIXES:
        value = Path(value).stem
    return value


def thumbnail_name(image_value: str) -> str:
    raw = str(image_value or "").split("?", 1)[0].strip()
    if not raw.startswith("assets/game-art/"):
        return ""
    source = Path(raw)
    if source.suffix.lower() not in RASTER_SUFFIXES:
        return ""
    stem = _strip_raster_suffixes(source.name).lower()
    return f"{stem}.jpg"


def _to_rgb(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _save_thumbnail(source: Path, destination: Path) -> int:
    try:
        with Image.open(source) as opened:
            rgb = _to_rgb(opened)
            thumb = ImageOps.fit(
                rgb,
                THUMB_SIZE,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
    except (UnidentifiedImageError, OSError) as exc:
        raise RuntimeError(f"thumbnail_source_invalid:{source.relative_to(ROOT)}") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    for quality in (84, 80, 76, 72):
        thumb.save(
            destination,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=False,
            subsampling=2,
        )
        if destination.stat().st_size <= MAX_BYTES:
            break

    size = destination.stat().st_size
    if size > MAX_BYTES:
        raise RuntimeError(f"thumbnail_too_large:{destination.name}:{size}")

    with Image.open(destination) as check:
        if check.format != "JPEG" or check.size != THUMB_SIZE:
            raise RuntimeError(f"thumbnail_validation_failed:{destination.name}")
    return size


def generate(output: Path) -> list[tuple[str, int]]:
    games_csv = ROOT / "games.csv"
    if not games_csv.exists():
        raise FileNotFoundError("missing_games_csv")

    generated: list[tuple[str, int]] = []
    seen: set[str] = set()
    with games_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            image_value = str(row.get("image") or "").strip()
            name = thumbnail_name(image_value)
            if not name or name in seen:
                continue
            seen.add(name)

            source = ROOT / image_value.split("?", 1)[0]
            if not source.exists() or not source.is_file() or source.is_symlink():
                raise FileNotFoundError(f"missing_thumbnail_source:{image_value}")

            destination = output / name
            size = _save_thumbnail(source, destination)
            generated.append((name, size))

    if not generated:
        raise RuntimeError("no_index_thumbnails_generated")
    return generated


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate lightweight JPEG thumbnails for the index.")
    parser.add_argument(
        "--output",
        default="_site/assets/game-thumbs",
        help="Thumbnail output directory (default: _site/assets/game-thumbs)",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    output = Path(args.output)
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    generated = generate(output)
    total = sum(size for _, size in generated)
    print(f"Generated {len(generated)} JPEG index thumbnails ({total} bytes total)")
    for name, size in generated:
        print(f"{name}\t{size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
