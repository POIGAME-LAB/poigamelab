#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROOT_FILES = (
    "index.html",
    "game.html",
    "guides.html",
    "offers.html",
    "kinoko-guide.html",
    "mementomori-guide.html",
    "township-lv60.html",
    "township-lv70.html",
    "whiteout-survival-guide.html",
    "working-heroes-guide.html",
    "tokyo-debunker-guide.html",
    "puzzles-survival-guide.html",
    "kingshot-guide.html",
    "houchishojo-guide.html",
    "evertale-guide.html",
    "data-status.html",
    "about.html",
    "privacy.html",
    "contact.html",
    "404.html",
    "games.csv",
    "games.js",
    "site-data.js",
    "site-footer.js",
    "site-referrals.js",
    "site-guides.js",
    "site-image-rights.js",
    "site-header.js",
    "poigamelab_hero.png",
    "poigamelab_icon.png",
    "poigamelab_logo_horizontal.png",
    "robots.txt",
)

DATA_FILES = (
    "published_offers.csv",
    "offer_history.csv",
    "refresh_status.json",
    "exception_queue.json",
)

CONFIG_FILES = (
    "refresh_policy.json",
)

PUBLIC_DIRS = (
    "assets",
)

DATA_DIRS = (
    "guide-experiences",
)

# Large artwork binaries are stored as small private binary chunks so no
# single connector upload is large enough to risk silent corruption. The
# public builder reconstructs the exact, locally-decoded high-quality WebP.
RECONSTRUCTED_GAME_ART = {
    "township": {
        "sha256": "394f7007846848626167ad450c7ef00b50394a0bf8582f32bec00ae90e455068",
        "size": 356920,
    },
    "kinoko": {
        "sha256": "89e207811bde0f3e14692cc24854799f2222b82b9b9ba53f18e9cbdfa72cbd5b",
        "size": 364828,
    },
    "whiteout-survival": {
        "sha256": "6777c8f3403d31eda027499562caeff4bb0953804e8b5c7f1090497600b4f710",
        "size": 511874,
    },
}


def _safe_source(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing_public_source:{path.relative_to(ROOT)}")
    if path.is_symlink():
        raise ValueError(f"symlink_public_source_rejected:{path.relative_to(ROOT)}")


def _copy_file(source: Path, destination: Path) -> None:
    _safe_source(source)
    if not source.is_file():
        raise ValueError(f"public_source_not_file:{source.relative_to(ROOT)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree(source: Path, destination: Path) -> None:
    _safe_source(source)
    if not source.is_dir():
        raise ValueError(f"public_source_not_directory:{source.relative_to(ROOT)}")
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink_public_source_rejected:{path.relative_to(ROOT)}")
        if path.is_file():
            relative = path.relative_to(source)
            _copy_file(path, destination / relative)


def _reconstruct_game_art(output: Path) -> None:
    source_root = ROOT / ".asset-source" / "game-art"
    for name, expected in RECONSTRUCTED_GAME_ART.items():
        source_dir = source_root / name
        _safe_source(source_dir)
        if not source_dir.is_dir():
            raise ValueError(f"game_art_source_not_directory:{name}")

        parts = sorted(source_dir.glob("*.part"))
        if not parts:
            raise ValueError(f"game_art_parts_missing:{name}")
        if any(part.is_symlink() or not part.is_file() for part in parts):
            raise ValueError(f"invalid_game_art_part:{name}")

        data = b"".join(part.read_bytes() for part in parts)
        if len(data) != expected["size"]:
            raise ValueError(
                f"game_art_size_mismatch:{name}:{len(data)}:{expected['size']}"
            )
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected["sha256"]:
            raise ValueError(f"game_art_sha256_mismatch:{name}:{digest}")
        if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise ValueError(f"game_art_webp_signature_invalid:{name}")

        destination = output / "assets" / "game-art" / f"{name}.webp"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def build_public_site(output: Path) -> list[str]:
    output = output.resolve()
    if output == ROOT or ROOT not in output.parents:
        # The builder is intended to write only into a disposable directory
        # beneath the repository working tree.
        raise ValueError("unsafe_output_directory")

    if output.exists():
        if output.is_symlink():
            raise ValueError("symlink_output_rejected")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for name in ROOT_FILES:
        _copy_file(ROOT / name, output / name)

    for name in DATA_FILES:
        _copy_file(ROOT / "data" / name, output / "data" / name)

    for name in CONFIG_FILES:
        _copy_file(ROOT / "config" / name, output / "config" / name)

    for name in DATA_DIRS:
        _copy_tree(ROOT / "data" / name, output / "data" / name)

    for name in PUBLIC_DIRS:
        _copy_tree(ROOT / name, output / name)

    _reconstruct_game_art(output)

    copied = sorted(
        str(path.relative_to(output)).replace("\\", "/")
        for path in output.rglob("*")
        if path.is_file()
    )
    return copied


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the explicit POIGAME LAB public-site artifact."
    )
    parser.add_argument(
        "--output",
        default="_site",
        help="Disposable output directory beneath the repository root (default: _site).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    output = (ROOT / args.output).resolve()
    copied = build_public_site(output)
    print(f"Built {len(copied)} public files in {output.relative_to(ROOT)}")
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
