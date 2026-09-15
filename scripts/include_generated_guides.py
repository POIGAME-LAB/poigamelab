#!/usr/bin/env python3
"""Add adopted generated guides to an already-built Pages artifact.

Fresh publication runs may still have full private content packages in the
workspace. Later deploys use only a compact hashed registry committed to the
repository, so research excerpts never need to remain in Git. Both paths fail
closed on catalog, path and file-integrity mismatches.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

import new_game_content_gate as gate

ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "data" / "new_game_content_packages"
REGISTRY = ROOT / "data" / "generated_guides_registry.json"
JS_MARKER = "/* POIGAME_GENERATED_GUIDES_V1 */"
XML_START = "<!-- POIGAME_GENERATED_GUIDES_V1_START -->"
XML_END = "<!-- POIGAME_GENERATED_GUIDES_V1_END -->"


def read_catalog(root):
    with (Path(root) / "games.csv").open(encoding="utf-8", newline="") as handle:
        return {str(row.get("name") or "").strip(): row for row in csv.DictReader(handle)
                if str(row.get("name") or "").strip()}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_guide_path(value):
    raw = str(value or "").strip().replace("\\", "/")
    return bool(raw and not raw.startswith("/") and "/" not in raw
                and ".." not in Path(raw).parts and raw.endswith("-guide.html"))


def safe_image_path(value):
    raw = str(value or "").strip().replace("\\", "/")
    return bool(raw.startswith("assets/game-art/") and not raw.startswith("/")
                and ".." not in Path(raw).parts and Path(raw).name)


def package_rows(root=ROOT, content_dir=CONTENT_DIR):
    root = Path(root)
    games = read_catalog(root)
    rows = {}
    if not Path(content_dir).exists():
        return rows
    for path in sorted(Path(content_dir).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"invalid_content_package_json:{path.name}") from exc
        game = str(payload.get("game") or "").strip()
        if not game or game not in games or payload.get("publicationReady") is not True:
            continue
        if game in rows:
            raise ValueError("duplicate_content_package_game:" + game)
        validated = gate.validate(payload, game, root=root, require_guide_file=True)
        guide = payload.get("guide") or {}
        rows[game] = {
            "game": game,
            "title": str(guide.get("title") or f"{game} ポイ活攻略"),
            "description": str(guide.get("overview") or ""),
            "guidePath": validated["guidePath"],
            "imagePath": validated["image"],
        }
    return rows


def registry_rows(root=ROOT, registry_path=REGISTRY):
    root = Path(root)
    path = Path(registry_path)
    if not path.exists():
        return {}
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("generated_guide_registry_invalid_json") from exc
    if registry.get("schemaVersion") != 1 or not isinstance(registry.get("guides"), dict):
        raise ValueError("generated_guide_registry_schema_invalid")
    games = read_catalog(root)
    rows = {}
    for game, raw in registry["guides"].items():
        if game not in games or not isinstance(raw, dict):
            raise ValueError("generated_guide_registry_catalog_mismatch:" + str(game))
        guide = str(raw.get("guidePath") or "")
        image = str(raw.get("imagePath") or "")
        if not safe_guide_path(guide) or not safe_image_path(image):
            raise ValueError("generated_guide_registry_path_invalid:" + game)
        guide_file, image_file = root / guide, root / image
        if (not guide_file.is_file() or guide_file.is_symlink()
                or not image_file.is_file() or image_file.is_symlink()):
            raise ValueError("generated_guide_registry_file_missing:" + game)
        if str(games[game].get("image") or "") != image:
            raise ValueError("generated_guide_registry_image_mismatch:" + game)
        expected_guide = str(raw.get("guideSha256") or "").lower()
        expected_image = str(raw.get("imageSha256") or "").lower()
        if len(expected_guide) != 64 or sha256(guide_file) != expected_guide:
            raise ValueError("generated_guide_registry_guide_hash_mismatch:" + game)
        if len(expected_image) != 64 or sha256(image_file) != expected_image:
            raise ValueError("generated_guide_registry_image_hash_mismatch:" + game)
        rows[game] = {
            "game": game,
            "title": str(raw.get("title") or f"{game} ポイ活攻略"),
            "description": str(raw.get("description") or ""),
            "guidePath": guide,
            "imagePath": image,
        }
    return rows


def eligible_rows(root=ROOT, content_dir=CONTENT_DIR, registry_path=REGISTRY):
    rows = registry_rows(root, registry_path)
    for game, row in package_rows(root, content_dir).items():
        existing = rows.get(game)
        if existing and existing != row:
            raise ValueError("generated_guide_registry_package_conflict:" + game)
        rows[game] = row
    return [rows[k] for k in sorted(rows)]


def patch_registry(artifact, rows):
    target = Path(artifact) / "site-guides.js"
    if not target.is_file():
        raise ValueError("artifact_site_guides_missing")
    entries = {
        row["game"]: {
            "title": row["title"],
            "description": row["description"],
            "links": [{"label": "攻略を読む →", "href": row["guidePath"]}],
        }
        for row in rows
    }
    base = target.read_text(encoding="utf-8").split(JS_MARKER, 1)[0].rstrip() + "\n"
    if entries:
        payload_js = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        base += JS_MARKER + "\n"
        base += "window.POIGAME_GUIDES=Object.freeze(Object.assign({},window.POIGAME_GUIDES||{}," + payload_js + "));\n"
    target.write_text(base, encoding="utf-8")


def patch_sitemap(artifact, rows):
    target = Path(artifact) / "sitemap.xml"
    if not target.is_file():
        raise ValueError("artifact_sitemap_missing")
    text = target.read_text(encoding="utf-8")
    if XML_START in text or XML_END in text:
        if XML_START not in text or XML_END not in text or text.index(XML_START) > text.index(XML_END):
            raise ValueError("artifact_generated_sitemap_marker_invalid")
        before, rest = text.split(XML_START, 1)
        _old, after = rest.split(XML_END, 1)
        text = before + after
    if "</urlset>" not in text:
        raise ValueError("artifact_sitemap_invalid")
    block = ""
    if rows:
        urls = [f'  <url><loc>https://poigamelab.com/{row["guidePath"]}</loc></url>' for row in rows]
        block = XML_START + "\n" + "\n".join(urls) + "\n" + XML_END + "\n"
    target.write_text(text.replace("</urlset>", block + "</urlset>"), encoding="utf-8")


def include(artifact, root=ROOT, content_dir=CONTENT_DIR, registry_path=REGISTRY):
    root = Path(root).resolve()
    artifact = Path(artifact).resolve()
    if not artifact.is_dir():
        raise ValueError("artifact_directory_missing")
    rows = eligible_rows(root=root, content_dir=content_dir, registry_path=registry_path)
    for row in rows:
        source = root / row["guidePath"]
        destination = artifact / row["guidePath"]
        shutil.copy2(source, destination)
    patch_registry(artifact, rows)
    patch_sitemap(artifact, rows)
    return [row["guidePath"] for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=ROOT / "_site")
    args = parser.parse_args(argv)
    guides = include(args.artifact)
    print(json.dumps({"generatedGuidesIncluded": len(guides), "guides": guides}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
