#!/usr/bin/env python3
"""Add every game that has a POIGAME LAB guide to the site catalog and the daily refresh.

Operator decision 2026-11-24: a game that gets a guide article is also shown in the game list and
its amounts are checked every day. config/guide_catalog.json holds the reviewed list text for each
such game (taken only from its guide). This script applies it, idempotently, to:

* games.csv                    - the public catalog (no image yet: the site shows its art fallback)
* config/refresh_policy.json   - daily refresh, enabled
* config/game_targets.json     - aliases + first-party offer URLs linked from the guide page
* docs/game-images/game-image-manifest.csv - records that the card has no image yet

    python scripts/sync_guide_games.py          # apply
    python scripts/sync_guide_games.py --check  # exit 1 if anything is missing (CI / routine)

--check also fails when a researched guide exists for a game that is neither in games.csv nor in
guide_catalog.json, so a new guide cannot be merged without registering its game.
No network, no API.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import direct_offer_refresh as direct  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CSV_FIELDS = ["name", "image", "condition", "days", "difficulty", "overview", "tips", "featured",
              "addedDate", "provisionalReward", "provisionalSource"]
NO_IMAGE_STATUS = "画像未作成・代替カード表示"
NO_IMAGE_SOURCE = "画像なし。サイト共通の文字だけの代替カードを表示（第三者画像の転載なし）"
REQUIRED = ("game", "guide", "addedDate", "aliases", "condition", "days", "difficulty", "overview", "tips")


def researched_guide_games(root: Path) -> dict[str, str]:
    """game -> first guide href, from site-researched-guides.js."""
    text = (root / "site-researched-guides.js").read_text(encoding="utf-8")
    out = {}
    for match in re.finditer(r'\n  "([^"]+)": \{\n    title: "[^"]*",\n    description: "[^"]*",\n'
                             r'    links: \[\n      \{ label: "[^"]*", href: "([^"]+)" \}', text):
        out.setdefault(match.group(1), match.group(2))
    return out


def guide_offer_urls(root: Path, href: str, sources: dict) -> dict[str, list[str]]:
    """Registered first-party offer detail URLs linked from the guide page, per source."""
    raw = (root / href).read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for url in re.findall(r'href="(https://[^"]+)"', raw):
        url = url.replace("&amp;", "&")
        for sid, source in sources.items():
            if source.get("acquisition_lane") == "device":
                continue
            if direct.source_host_allowed(url, source) and direct.detail_like(url, source):
                try:
                    identity = direct.offer_identity_key(url, sid)
                except Exception:
                    identity = None
                if identity and url not in found.setdefault(sid, []):
                    found[sid].append(url)
    return {sid: urls for sid, urls in sorted(found.items()) if urls}


def load(root: Path):
    catalog_cfg = json.loads((root / "config/guide_catalog.json").read_text(encoding="utf-8"))
    entries = catalog_cfg["games"]
    for entry in entries:
        missing = [k for k in REQUIRED if not entry.get(k)]
        if missing:
            raise ValueError(f"guide_catalog entry {entry.get('game')!r} missing {missing}")
        if entry["game"] not in entry["aliases"]:
            raise ValueError(f"guide_catalog entry {entry['game']!r}: aliases must include the game name")
    return entries


def problems(root: Path = ROOT) -> list[str]:
    entries = load(root)
    names = {e["game"] for e in entries}
    catalog = [r["name"] for r in csv.DictReader((root / "games.csv").open(encoding="utf-8"))]
    policy = json.loads((root / "config/refresh_policy.json").read_text(encoding="utf-8"))["games"]
    targets = {t["game"] for t in json.loads((root / "config/game_targets.json").read_text(encoding="utf-8"))["games"]}
    manifest_path = root / "docs/game-images/game-image-manifest.csv"
    manifest = ({r["name"] for r in csv.DictReader(manifest_path.open(encoding="utf-8-sig"))}
                if manifest_path.is_file() else None)
    out = []
    for game, href in researched_guide_games(root).items():
        if game not in catalog and game not in names:
            out.append(f"guide without catalog entry: {game} ({href}) - add it to config/guide_catalog.json")
    for entry in entries:
        game = entry["game"]
        if not (root / entry["guide"]).is_file():
            out.append(f"guide page missing: {entry['guide']}")
        if game not in catalog:
            out.append(f"not in games.csv: {game}")
        if game not in policy:
            out.append(f"not in refresh_policy: {game}")
        if game not in targets:
            out.append(f"not in game_targets: {game}")
        if manifest is not None and game not in manifest:
            out.append(f"not in game-image manifest: {game}")
    return out


def apply(root: Path = ROOT) -> list[str]:
    entries = load(root)
    sources = {s["id"]: s for s in json.loads((root / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
    changed = []

    # games.csv: append rows only (existing rows are never rewritten)
    csv_path = root / "games.csv"
    text = csv_path.read_text(encoding="utf-8")
    header = text.split("\n", 1)[0].split(",")
    if header != CSV_FIELDS:
        raise ValueError("games.csv header changed; update CSV_FIELDS after review")
    catalog = {r["name"] for r in csv.DictReader(io.StringIO(text))}
    new_rows = []
    for e in entries:
        if e["game"] in catalog:
            continue
        new_rows.append({"name": e["game"], "image": "", "condition": e["condition"], "days": e["days"],
                         "difficulty": e["difficulty"], "overview": e["overview"], "tips": e["tips"],
                         "featured": "false", "addedDate": e["addedDate"], "provisionalReward": "",
                         "provisionalSource": ""})
    if new_rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writerows(new_rows)
        csv_path.write_text(text.rstrip("\n") + "\n" + buf.getvalue(), encoding="utf-8")
        changed.append(f"games.csv +{len(new_rows)}")

    # docs/game-images/game-image-manifest.csv: record that the card has no image yet
    manifest_path = root / "docs/game-images/game-image-manifest.csv"
    if manifest_path.is_file():
        raw = manifest_path.read_bytes().decode("utf-8-sig")
        eol = "\r\n" if "\r\n" in raw else "\n"
        mtext = raw.replace("\r\n", "\n")
        listed = {r["name"] for r in csv.DictReader(io.StringIO(mtext))}
        fields = mtext.split("\n", 1)[0].split(",")
        rows = [{**{f: "" for f in fields}, "name": e["game"], "production_status": NO_IMAGE_STATUS,
                 "source_and_license": NO_IMAGE_SOURCE} for e in entries if e["game"] not in listed]
        if rows:
            buf = io.StringIO()
            csv.DictWriter(buf, fieldnames=fields, lineterminator="\n").writerows(rows)
            out_text = (mtext.rstrip("\n") + "\n" + buf.getvalue()).replace("\n", eol)
            manifest_path.write_bytes(("\ufeff" + out_text).encode("utf-8"))
            changed.append(f"image manifest +{len(rows)}")

    # refresh_policy.json
    policy_path = root / "config/refresh_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    added = 0
    for e in entries:
        if e["game"] not in policy["games"]:
            policy["games"][e["game"]] = {"enabled": True, "supplementalSources": [],
                                          "adoptedBy": f"GUIDE_{e['addedDate'].replace('-', '_')}"}
            added += 1
    if added:
        policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(f"refresh_policy +{added}")

    # game_targets.json: append blocks in the file's own style
    targets_path = root / "config/game_targets.json"
    ttext = targets_path.read_text(encoding="utf-8")
    known = {t["game"] for t in json.loads(ttext)["games"]}
    blocks = []
    for e in entries:
        if e["game"] in known:
            continue
        urls = guide_offer_urls(root, e["guide"], sources)
        inner = ",\n".join(f'        {json.dumps(sid)}: {json.dumps(v, ensure_ascii=False)}' for sid, v in urls.items())
        known_block = "{\n" + inner + "\n      }" if urls else "{}"
        blocks.append('    {\n      "game": %s,\n      "aliases": %s,\n      "known_urls_by_source": %s\n    }'
                      % (json.dumps(e["game"], ensure_ascii=False), json.dumps(e["aliases"], ensure_ascii=False), known_block))
    if blocks:
        if not ttext.endswith("    }\n  ]\n}\n"):
            raise ValueError("game_targets.json layout changed; append manually")
        ttext = ttext[:-len("\n  ]\n}\n")] + ",\n" + ",\n".join(blocks) + "\n  ]\n}\n"
        json.loads(ttext)
        targets_path.write_text(ttext, encoding="utf-8")
        changed.append(f"game_targets +{len(blocks)}")
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        found = problems()
        for line in found:
            print("ERROR:", line)
        print("guide games:", "ok" if not found else f"{len(found)} problem(s)")
        return 1 if found else 0
    print("applied:", ", ".join(apply()) or "nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
