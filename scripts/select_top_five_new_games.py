#!/usr/bin/env python3
"""Select the five highest verified-reward unlisted games from the unified crawl snapshot.

This stage is deliberately independent from crawling and existing-game publication.
It never fetches the network and never authorizes publication. A game is ranking-
eligible when at least one first-party offer in the unified snapshot has a verified,
positive JPY reward. Multiple point-site offers for the same game are already grouped
by the upstream snapshot; this selector ranks each game by its highest verified JPY
reward and keeps all verified point-site evidence for downstream research.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "unified_offer_snapshot.json"
GAMES = ROOT / "games.csv"
OUTPUT = ROOT / "data" / "top_five_new_game_candidates.json"
MAX_GAMES = 5


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def norm(value):
    return re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠]+", "", str(value or "").casefold())


def existing_games(path=GAMES):
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {norm(row.get("name")) for row in csv.DictReader(handle) if row.get("name")}


def safe_https(value):
    try:
        parsed = urlparse(str(value or "").strip())
    except Exception:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return str(value).strip()


def research_queries(game):
    return {
        "web": f'"{game}" ポイ活 攻略 達成 撤退',
        "x": f'site:x.com "{game}" ポイ活 日目',
        "youtube": f'site:youtube.com "{game}" ポイ活 攻略',
        "instagram": f'site:instagram.com "{game}" ポイ活',
        "pointSites": f'"{game}" ポイ活 口コミ 課金',
    }


def _source_health(snapshot):
    source_ids = [str(x or "").strip() for x in snapshot.get("sourceIds") or [] if str(x or "").strip()]
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError("snapshot_source_ids_invalid")
    if int(snapshot.get("sourceCount") or 0) != len(source_ids):
        raise ValueError("snapshot_source_count_mismatch")
    health = {}
    for row in snapshot.get("sourceHealth") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        if source:
            health[source] = row
    incomplete = [source for source in source_ids if health.get(source, {}).get("scanComplete") is not True]
    return source_ids, sorted(incomplete)


def _verified_offers(group):
    rows = []
    for offer in group.get("offers") or []:
        if not isinstance(offer, dict) or offer.get("rewardVerified") is not True:
            continue
        reward = offer.get("rewardYen")
        if type(reward) is not int or reward <= 0:
            continue
        source = str(offer.get("source") or "").strip()
        url = safe_https(offer.get("url"))
        if not source or not url:
            continue
        rows.append({
            "source": source,
            "url": url,
            "platform": str(offer.get("platform") or ""),
            "rewardYen": reward,
            "parserVersion": str(offer.get("parserVersion") or ""),
            "offerIdentity": str(offer.get("offerIdentity") or ""),
        })
    rows.sort(key=lambda row: (-row["rewardYen"], row["source"], row["url"]))
    return rows


def build(snapshot, *, known_games=None, limit=MAX_GAMES):
    if not isinstance(snapshot, dict) or snapshot.get("phase") != "UNIFIED_EIGHT_SITE_OFFER_SNAPSHOT_V1":
        raise ValueError("snapshot_phase_mismatch")
    if snapshot.get("publicationAuthorized") is not False:
        raise ValueError("snapshot_publication_boundary_invalid")
    checked_at = str(snapshot.get("checkedAt") or "").strip()
    if not checked_at:
        raise ValueError("snapshot_checked_at_missing")

    source_ids, incomplete_sources = _source_health(snapshot)
    if incomplete_sources:
        return {
            "schemaVersion": 1,
            "phase": "TOP_FIVE_NEW_GAME_SELECTION_V1",
            "checkedAt": checked_at,
            "sourcePhase": snapshot.get("phase"),
            "candidateOnly": True,
            "publicationAuthorized": False,
            "oneVerifiedSiteEligible": True,
            "rankingBasis": "max_verified_reward_yen_per_grouped_game",
            "rankingComplete": False,
            "holdReason": "source_scan_incomplete",
            "incompleteSources": incomplete_sources,
            "sourceIds": source_ids,
            "eligibleGameCount": 0,
            "count": 0,
            "items": [],
        }

    known = set(known_games or [])
    seen_keys = set()
    candidates = []
    for group in snapshot.get("groups") or []:
        if not isinstance(group, dict):
            continue
        game = str(group.get("game") or "").strip()
        game_key = str(group.get("gameKey") or "").strip()
        if not game or not game_key:
            continue
        if game_key in seen_keys:
            raise ValueError("snapshot_duplicate_game_key")
        seen_keys.add(game_key)
        if group.get("listed") is True or norm(game) in known:
            continue

        offers = _verified_offers(group)
        if not offers:
            continue
        max_reward = offers[0]["rewardYen"]
        aggregate = group.get("maxVerifiedRewardYen")
        if type(aggregate) is not int or aggregate != max_reward:
            raise ValueError("snapshot_reward_aggregate_mismatch")

        verified_sources = sorted({row["source"] for row in offers})
        candidates.append({
            "gameKey": game_key,
            "game": game,
            "maxVerifiedRewardYen": max_reward,
            "verifiedSourceCount": len(verified_sources),
            "verifiedSources": verified_sources,
            "verifiedOfferCount": len(offers),
            "bestOffer": dict(offers[0]),
            "pointSiteEvidence": offers,
            "researchQueries": research_queries(game),
            "publicationAuthorized": False,
        })

    candidates.sort(key=lambda row: (-row["maxVerifiedRewardYen"], row["game"].casefold(), row["gameKey"]))
    limit = max(0, int(limit))
    selected = candidates[:limit]
    for rank, row in enumerate(selected, 1):
        row["rank"] = rank

    return {
        "schemaVersion": 1,
        "phase": "TOP_FIVE_NEW_GAME_SELECTION_V1",
        "checkedAt": checked_at,
        "sourcePhase": snapshot.get("phase"),
        "candidateOnly": True,
        "publicationAuthorized": False,
        "oneVerifiedSiteEligible": True,
        "rankingBasis": "max_verified_reward_yen_per_grouped_game",
        "rankingComplete": True,
        "holdReason": None,
        "incompleteSources": [],
        "sourceIds": source_ids,
        "eligibleGameCount": len(candidates),
        "count": len(selected),
        "items": selected,
    }


def write(input_path=INPUT, games_path=GAMES, output_path=OUTPUT, limit=MAX_GAMES):
    out = build(load_json(input_path), known_games=existing_games(games_path), limit=limit)
    atomic_json(output_path, out)
    return out


def main():
    out = write()
    print(json.dumps({
        "phase": out["phase"],
        "rankingComplete": out["rankingComplete"],
        "eligible": out["eligibleGameCount"],
        "selected": out["count"],
        "publicationAuthorized": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
