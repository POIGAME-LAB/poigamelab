#!/usr/bin/env python3
"""Add validated new-game guides to an already-built Pages artifact.

Only games already present in games.csv are exposed. Research packages themselves
stay private; the public artifact receives only the rendered guide HTML, a compact
guide registry entry and sitemap URLs. Any adopted game with an invalid package
fails closed before deployment.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import new_game_content_gate as gate

ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "data" / "new_game_content_packages"


def catalog_games(root):
    with (Path(root) / "games.csv").open(encoding="utf-8", newline="") as handle:
        return {str(row.get("name") or "").strip() for row in csv.DictReader(handle) if str(row.get("name") or "").strip()}


def eligible_packages(root=ROOT, content_dir=CONTENT_DIR):
    root = Path(root)
    content_dir = Path(content_dir)
    games = catalog_games(root)
    rows = []
    if not content_dir.exists():
        return rows
    seen = set()
    for path in sorted(content_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"invalid_content_package_json:{path.name}") from exc
        game = str(payload.get("game") or "").strip()
        if not game or game not in games or payload.get("publicationReady") is not True:
            continue
        if game in seen:
            raise ValueError("duplicate_content_package_game:" + game)
        validated = gate.validate(payload, game, root=root, require_guide_file=True)
        rows.append((payload, validated))
        seen.add(game)
    return rows


def patch_registry(artifact, rows):
    target = Path(artifact) / "site-guides.js"
    if not target.is_file():
        raise ValueError("artifact_site_guides_missing")
    entries = {}
    for payload, validated in rows:
        guide = payload["guide"]
        entries[validated["game"]] = {
            "title": str(guide["title"]),
            "description": str(guide["overview"]),
            "links": [{"label": "攻略を読む →", "href": validated["guidePath"]}],
        }
    marker = "/* POIGAME_GENERATED_GUIDES_V1 */"
    base = target.read_text(encoding="utf-8").split(marker, 1)[0].rstrip() + "\n"
    if entries:
        payload_js = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        base += (
            marker + "\n" +
            "window.POIGAME_GUIDES=Object.freeze(Object.assign({},window.POIGAME_GUIDES||{}," + payload_js + "));\n"
        )
    target.write_text(base, encoding="utf-8")


def patch_sitemap(artifact, rows):
    target = Path(artifact) / "sitemap.xml"
    if not target.is_file():
        raise ValueError("artifact_sitemap_missing")
    text = target.read_text(encoding="utf-8")
    if "</urlset>" not in text:
        raise ValueError("artifact_sitemap_invalid")
    inserts = []
    for _payload, validated in rows:
        loc = f'https://poigamelab.com/{validated["guidePath"]}'
        if loc not in text:
            inserts.append(f"  <url><loc>{loc}</loc></url>\n")
    if inserts:
        text = text.replace("</urlset>", "".join(inserts) + "</urlset>")
        target.write_text(text, encoding="utf-8")


def include(artifact, root=ROOT, content_dir=CONTENT_DIR):
    root = Path(root).resolve()
    artifact = Path(artifact).resolve()
    if not artifact.is_dir():
        raise ValueError("artifact_directory_missing")
    rows = eligible_packages(root=root, content_dir=content_dir)
    for _payload, validated in rows:
        source = root / validated["guidePath"]
        destination = artifact / validated["guidePath"]
        if source.is_symlink():
            raise ValueError("guide_symlink_rejected")
        shutil.copy2(source, destination)
    patch_registry(artifact, rows)
    patch_sitemap(artifact, rows)
    return [validated["guidePath"] for _payload, validated in rows]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    guides = include(args.artifact)
    print(json.dumps({"generatedGuidesIncluded": len(guides), "guides": guides}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
