#!/usr/bin/env python3
"""Write a compact handoff queue for the five new games selected by the 01:17 scan.

The queue contains no publication permission. It exposes only the reviewed game
identity, verified point-site reward ranking metadata, first-party detail URLs and
research queries needed by the later content-research stage. If the bounded
ranking scan is incomplete, the handoff is deliberately empty so an unreviewed
candidate cannot be mislabeled as a daily top-five game.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "daily_scan_review.json"
OUTPUT = ROOT / "data" / "new_game_content_queue.json"
CATALOG = ROOT / "games.csv"
TARGETS = ROOT / "config" / "game_targets.json"
REQUIRED_CHANNELS = ["web", "x", "youtube", "instagram", "pointSites"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def game_key(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def load_catalog_games(path=CATALOG):
    path = Path(path)
    if not path.is_file():
        raise ValueError("public_game_catalog_missing")
    with path.open(encoding="utf-8", newline="") as handle:
        games = {
            str(row.get("name") or "").strip()
            for row in csv.DictReader(handle)
            if str(row.get("name") or "").strip()
        }
    if not games:
        raise ValueError("public_game_catalog_empty")
    return games


def load_target_aliases(path=TARGETS):
    """Reviewed names of listed games, e.g. a subtitled store title.

    A missing file adds nothing; games.csv stays the authoritative catalog.
    """
    path = Path(path)
    if not path.is_file():
        return set()
    names = set()
    for target in (load(path).get("games") or []):
        if not isinstance(target, dict):
            continue
        for name in [target.get("game")] + list(target.get("aliases") or []):
            if str(name or "").strip():
                names.add(str(name).strip())
    return names


def safe_https(value):
    try:
        p = urlparse(str(value or "").strip())
    except Exception:
        return ""
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return ""
    return str(value).strip()


def empty_handoff(report, reason):
    return {
        "schemaVersion": 1,
        "phase": "NEW_GAME_CONTENT_QUEUE_V1",
        "checkedAt": report.get("checkedAt"),
        "sourcePhase": report.get("phase"),
        "candidateOnly": True,
        "publicationAuthorized": False,
        "rankingComplete": False,
        "holdReason": reason,
        "count": 0,
        "items": [],
    }


def build(report, existing_games=None):
    if not isinstance(report, dict) or report.get("phase") != "DAILY_SAME_SCAN_REVIEW_V1":
        raise ValueError("daily_review_phase_mismatch")
    top = report.get("topFiveReviewCandidates")
    results = report.get("results")
    if not isinstance(top, list) or not isinstance(results, list):
        raise ValueError("daily_review_shape_invalid")
    if report.get("groupLimitReached") is True:
        return empty_handoff(report, "ranking_group_budget_reached")
    if report.get("detailLimitReached") is True:
        return empty_handoff(report, "ranking_detail_budget_reached")
    if report.get("rankingComplete") is False:
        return empty_handoff(report, "ranking_incomplete")

    by_game = {str(row.get("game") or ""): row for row in results if isinstance(row, dict)}
    existing_keys = {
        game_key(game)
        for game in (existing_games or [])
        if str(game or "").strip()
    }

    # topFiveReviewCandidates is authoritative for the current run, but a
    # stale/generated report can still contain a catalogued game. Extend the
    # pool with the remaining ranked results so skipping an existing game can
    # safely promote the next genuinely new candidate instead of shrinking the
    # handoff unnecessarily.
    ranked_pool = []
    seen = set()
    for game in top:
        game = str(game or "").strip()
        if game and game not in seen:
            ranked_pool.append(game)
            seen.add(game)
    remainder = sorted(
        (
            row for row in results
            if isinstance(row, dict)
            and row.get("candidateEligible") is True
            and type(row.get("maxObservedRewardYen")) is int
            and row.get("maxObservedRewardYen") > 0
        ),
        key=lambda row: (-row["maxObservedRewardYen"], str(row.get("game") or "")),
    )
    for row in remainder:
        game = str(row.get("game") or "").strip()
        if game and game not in seen:
            ranked_pool.append(game)
            seen.add(game)

    items = []
    for game in ranked_pool:
        if len(items) >= 5:
            break
        game = str(game or "").strip()
        if game_key(game) in existing_keys:
            continue
        row = by_game.get(game)
        if not game or not isinstance(row, dict):
            raise ValueError("ranked_game_missing_from_results")
        if row.get("publicationAuthorized") is not False or row.get("candidateEligible") is not True:
            raise ValueError("ranked_game_not_quarantined_candidate")
        amount = row.get("maxObservedRewardYen")
        if type(amount) is not int or amount <= 0:
            raise ValueError("ranked_game_reward_invalid")
        queries = row.get("researchQueries")
        if not isinstance(queries, dict):
            raise ValueError("ranked_game_queries_missing")
        required_query_keys = {"web", "x", "youtube", "instagram", "point_site_reviews"}
        if not required_query_keys.issubset(queries):
            raise ValueError("ranked_game_queries_incomplete")
        point_sites = []
        verified_reward_sources = 0
        for detail in row.get("details") or []:
            if not isinstance(detail, dict):
                continue
            url = safe_https(detail.get("finalUrl") or detail.get("url"))
            sid = str(detail.get("source") or "").strip()
            reward = detail.get("rewardYen")
            if url and sid:
                point_sites.append({
                    "source": sid,
                    "url": url,
                    "detailConfirmed": detail.get("detailConfirmed") is True,
                    "rewardVerified": type(reward) is int and reward > 0,
                    "rewardYen": reward if type(reward) is int and reward > 0 else None,
                })
                if type(reward) is int and reward > 0:
                    verified_reward_sources += 1
        dedup = {(x["source"], x["url"]): x for x in point_sites}
        if len({x[0] for x in dedup}) < 2:
            raise ValueError("ranked_game_listing_sources_below_two")
        if verified_reward_sources < 1:
            raise ValueError("ranked_game_verified_reward_missing")
        items.append({
            "rank": len(items) + 1,
            "game": game,
            "maxObservedRewardYen": amount,
            "confirmedSourceCount": int(row.get("confirmedSourceCount") or 0),
            "listingSourceCount": int(row.get("listingSourceCount") or len({x[0] for x in dedup})),
            "verifiedRewardSourceCount": int(row.get("verifiedRewardSourceCount") or verified_reward_sources),
            "pointSiteEvidence": list(dedup.values()),
            "researchQueries": {
                "web": str(queries["web"]),
                "x": str(queries["x"]),
                "youtube": str(queries["youtube"]),
                "instagram": str(queries["instagram"]),
                "pointSites": str(queries["point_site_reviews"]),
            },
            "requiredResearchChannels": list(REQUIRED_CHANNELS),
            "contentPackageStatus": "pending",
            "publicationAuthorized": False,
        })
    return {
        "schemaVersion": 1,
        "phase": "NEW_GAME_CONTENT_QUEUE_V1",
        "checkedAt": report.get("checkedAt"),
        "sourcePhase": report.get("phase"),
        "candidateOnly": True,
        "publicationAuthorized": False,
        "rankingComplete": True,
        "holdReason": None,
        "count": len(items),
        "items": items,
    }


def write(input_path=INPUT, output_path=OUTPUT, catalog_path=CATALOG, targets_path=TARGETS):
    existing = load_catalog_games(catalog_path) | load_target_aliases(targets_path)
    out = build(load(input_path), existing_games=existing)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return out


def main():
    out = write()
    print(json.dumps({
        "phase": out["phase"],
        "count": out["count"],
        "rankingComplete": out["rankingComplete"],
        "publicationAuthorized": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
