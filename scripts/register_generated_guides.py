#!/usr/bin/env python3
"""Persist compact public metadata for adopted generated guides.

Full research/content packages remain quarantined. Only title, description,
reachable paths and content hashes are kept in the repository registry. The
source guide registry and sitemap are regenerated from this compact state so
later builds do not need private research artifacts.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import new_game_content_gate as gate

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "data" / "new_game_content_packages"
REGISTRY = ROOT / "data" / "generated_guides_registry.json"
GUIDES_JS = ROOT / "site-guides.js"
SITEMAP = ROOT / "sitemap.xml"
JS_MARKER = "/* POIGAME_GENERATED_GUIDES_V1 */"
XML_START = "<!-- POIGAME_GENERATED_GUIDES_V1_START -->"
XML_END = "<!-- POIGAME_GENERATED_GUIDES_V1_END -->"


def load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError, TypeError):
        return default


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_guide_path(value):
    raw = str(value or "").strip().replace("\\", "/")
    return bool(raw and not raw.startswith("/") and "/" not in raw
                and ".." not in Path(raw).parts and raw.endswith("-guide.html"))


def catalog(root=ROOT):
    with (Path(root) / "games.csv").open(encoding="utf-8", newline="") as handle:
        return {str(row.get("name") or "").strip(): row for row in csv.DictReader(handle)
                if str(row.get("name") or "").strip()}


def merge_registry(root=ROOT, content_dir=CONTENT, registry_path=REGISTRY):
    root = Path(root)
    existing = load_json(registry_path, {"schemaVersion": 1, "guides": {}})
    guides = existing.get("guides") if isinstance(existing.get("guides"), dict) else {}
    guides = dict(guides)
    games = catalog(root)
    added = []
    for path in sorted(Path(content_dir).glob("*.json")) if Path(content_dir).exists() else []:
        payload = load_json(path, {})
        game = str(payload.get("game") or "").strip()
        if not game or game not in games or payload.get("publicationReady") is not True:
            continue
        validated = gate.validate(payload, game, root=root, require_guide_file=True)
        guide = payload.get("guide") or {}
        guide_path = validated["guidePath"]
        image_path = validated["image"]
        if str(games[game].get("image") or "") != image_path:
            raise ValueError("catalog_generated_image_mismatch:" + game)
        entry = {
            "title": str(guide.get("title") or f"{game} ポイ活攻略"),
            "description": str(guide.get("overview") or ""),
            "guidePath": guide_path,
            "guideSha256": sha256(root / guide_path),
            "imagePath": image_path,
            "imageSha256": sha256(root / image_path),
        }
        if guides.get(game) != entry:
            guides[game] = entry
            added.append(game)
    out = {"schemaVersion": 1, "guides": dict(sorted(guides.items()))}
    atomic_text(registry_path, json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    return out, added


def patch_guides_js(registry, path=GUIDES_JS):
    target = Path(path)
    base = target.read_text(encoding="utf-8").split(JS_MARKER, 1)[0].rstrip() + "\n"
    entries = {}
    for game, row in (registry.get("guides") or {}).items():
        guide_path = str(row.get("guidePath") or "")
        if not safe_guide_path(guide_path):
            raise ValueError("generated_guide_path_invalid")
        entries[game] = {
            "title": str(row.get("title") or f"{game} ポイ活攻略"),
            "description": str(row.get("description") or ""),
            "links": [{"label": "攻略を読む →", "href": guide_path}],
        }
    if entries:
        encoded = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        base += JS_MARKER + "\n"
        base += "window.POIGAME_GUIDES=Object.freeze(Object.assign({},window.POIGAME_GUIDES||{}," + encoded + "));\n"
    atomic_text(target, base)


def patch_sitemap(registry, path=SITEMAP):
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if XML_START in text or XML_END in text:
        if XML_START not in text or XML_END not in text or text.index(XML_START) > text.index(XML_END):
            raise ValueError("generated_sitemap_marker_invalid")
        before, rest = text.split(XML_START, 1)
        _old, after = rest.split(XML_END, 1)
        text = before + after
    if "</urlset>" not in text:
        raise ValueError("sitemap_urlset_missing")
    rows = []
    seen = set()
    for row in (registry.get("guides") or {}).values():
        guide = str(row.get("guidePath") or "")
        if not safe_guide_path(guide) or guide in seen:
            raise ValueError("generated_guide_path_invalid")
        seen.add(guide)
        rows.append(f"  <url><loc>https://poigamelab.com/{guide}</loc></url>")
    block = ""
    if rows:
        block = XML_START + "\n" + "\n".join(rows) + "\n" + XML_END + "\n"
    text = text.replace("</urlset>", block + "</urlset>")
    atomic_text(target, text)


def run(root=ROOT, content_dir=CONTENT, registry_path=REGISTRY, guides_js=GUIDES_JS, sitemap=SITEMAP):
    registry, added = merge_registry(root=root, content_dir=content_dir, registry_path=registry_path)
    patch_guides_js(registry, guides_js)
    patch_sitemap(registry, sitemap)
    return {"registered": len(registry.get("guides") or {}), "addedOrUpdated": added}


def main():
    print(json.dumps(run(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
