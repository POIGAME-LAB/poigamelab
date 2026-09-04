#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROOT_FILES = (
    "index.html",
    "game.html",
    "kinoko-guide.html",
    "mementomori-guide.html",
    "township-lv60.html",
    "township-lv70.html",
    "whiteout-survival-guide.html",
    "working-heroes-guide.html",
    "data-status.html",
    "about.html",
    "privacy.html",
    "contact.html",
    "404.html",
    "games.csv",
    "games.js",
    "site-data.js",
    "site-footer.js",
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

    for name in PUBLIC_DIRS:
        _copy_tree(ROOT / name, output / name)

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
