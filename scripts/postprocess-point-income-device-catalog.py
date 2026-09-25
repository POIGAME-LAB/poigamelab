#!/usr/bin/env python3
"""Post-process a validated Point Income residential-device catalog.

The input is already candidate-only. This step conservatively:
- matches current POIGAME LAB games using reviewed aliases;
- groups iOS/Android variants per game;
- keeps unmatched app rows in a separate review queue;
- never authorizes publication.
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

REVIEWED_ALIASES = {
    "Township": ["Township", "タウンシップ"],
    "きのこ伝説": ["きのこ伝説"],
    "メメントモリ": ["メメントモリ", "MementoMori", "Memento Mori"],
    "ワーキングヒーロー": ["ワーキングヒーロー", "Working Hero"],
    "ホワイトアウト・サバイバル": [
        "ホワイトアウト・サバイバル",
        "Whiteout Survival",
    ],
    "東京ディバンカー": ["東京ディバンカー", "Tokyo Debunker"],
    "パズル＆サバイバル": [
        "パズル＆サバイバル",
        "パズル&サバイバル",
        "Puzzles & Survival",
        "Puzzles and Survival",
    ],
    "キングショット": ["キングショット", "Kingshot"],
    "放置少女": ["放置少女"],
    "エバーテイル": ["エバーテイル", "Evertale"],
    "ATLAS: EARTH": ["ATLAS: EARTH", "ATLAS:EARTH", "ATLAS EARTH"],
    "ファミリーファームの冒険": [
        "ファミリーファームの冒険",
        "Family Farm Adventure",
    ],
    "クロンダイクの冒険": ["クロンダイクの冒険", "Klondike Adventures"],
    "Merge Help: ホームデザインパズル": [
        "Merge Help",
        "ホームデザインパズル",
    ],
    "マジックジグソーパズル": [
        "マジックジグソーパズル",
        "Magic Jigsaw Puzzles",
    ],
    "Sea Block 1010": ["Sea Block 1010"],
    "さる山温泉旅館": ["さる山温泉旅館"],
    "インポッシブルカート": ["インポッシブルカート", "Impossible Cart"],
    "天地英雄伝": ["天地英雄伝"],
    "High Roller Vegas": ["High Roller Vegas", "ハイローラーベガス"],
}

PROMO_PATTERNS = [
    r"【[^】]*】",
    r"\[[^\]]*\]",
    r"（(?:iOS|Android|iPhone)用）",
    r"\((?:iOS|Android|iPhone)用\)",
]


def norm(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for pat in PROMO_PATTERNS:
        text = re.sub(pat, " ", text, flags=re.I)
    text = text.replace("＆", "&")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[・･·／/｜|：:‐-‒–—―_\-]+", "", text)
    text = re.sub(r"[【】\[\]（）()「」『』〈〉《》]", "", text)
    return text[:320]


def load_games(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [str(row.get("name") or "").strip() for row in rows if str(row.get("name") or "").strip()]


def alias_index(games):
    out = {}
    for game in games:
        aliases = REVIEWED_ALIASES.get(game, [game])
        vals = []
        for alias in aliases:
            key = norm(alias)
            if key and key not in vals:
                vals.append(key)
        out[game] = vals
    return out


def match_game(title, index):
    key = norm(title)
    hits = []
    for game, aliases in index.items():
        if any(alias and alias in key for alias in aliases):
            hits.append(game)
    return hits[0] if len(hits) == 1 else ""


def main(inp, games_csv, matched_out, unmatched_out):
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    offers = data.get("offers")
    if not isinstance(offers, list):
        raise SystemExit("validated catalog must contain offers")

    games = load_games(games_csv)
    index = alias_index(games)
    matched = []
    unmatched = []

    for item in offers:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        game = match_game(title, index)
        row = {
            "source": "point_income",
            "game": game,
            "adId": str(item.get("adId") or ""),
            "url": str(item.get("url") or ""),
            "title": title,
            "platform": str(item.get("platform") or ""),
            "currentPoints": item.get("currentPoints"),
            "currentYen": item.get("currentYen"),
            "candidateOnly": True,
            "publicationAuthorized": False,
        }
        if game:
            matched.append(row)
        elif row["platform"] in {"iOS", "Android", "iOS|Android"}:
            unmatched.append(row)

    by_game = {}
    for row in matched:
        by_game.setdefault(row["game"], []).append(row)

    groups = []
    for game in games:
        rows = by_game.get(game, [])
        if not rows:
            continue
        valid_yen = [
            x["currentYen"]
            for x in rows
            if isinstance(x.get("currentYen"), (int, float))
        ]
        groups.append({
            "game": game,
            "candidateOnly": True,
            "publicationAuthorized": False,
            "bestDisplayedYen": max(valid_yen) if valid_yen else None,
            "offers": rows,
        })

    matched_payload = {
        "phase": "POINT_INCOME_EXISTING_GAME_CANDIDATES_V1",
        "source": "point_income",
        "candidateOnly": True,
        "publicationAuthorized": False,
        "catalogCount": int(data.get("count") or len(offers)),
        "matchedOfferCount": len(matched),
        "matchedGameCount": len(groups),
        "items": groups,
    }
    unmatched_payload = {
        "phase": "POINT_INCOME_UNMATCHED_APP_CANDIDATES_V1",
        "source": "point_income",
        "candidateOnly": True,
        "publicationAuthorized": False,
        "count": len(unmatched),
        "items": unmatched,
    }

    Path(matched_out).write_text(
        json.dumps(matched_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(unmatched_out).write_text(
        json.dumps(unmatched_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "matchedGameCount": len(groups),
        "matchedOfferCount": len(matched),
        "unmatchedAppCandidateCount": len(unmatched),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
