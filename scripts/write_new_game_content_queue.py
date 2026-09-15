#!/usr/bin/env python3
"""Write a compact handoff queue for the five new games selected by the 01:17 scan.

The queue contains no publication permission.  It exposes only the reviewed game
identity, verified point-site reward ranking metadata, first-party detail URLs and
research queries needed by the later content-research stage.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "daily_scan_review.json"
OUTPUT = ROOT / "data" / "new_game_content_queue.json"
REQUIRED_CHANNELS = ["web", "x", "youtube", "instagram", "pointSites"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def safe_https(value):
    try:
        p = urlparse(str(value or "").strip())
    except Exception:
        return ""
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return ""
    return str(value).strip()


def build(report):
    if not isinstance(report, dict) or report.get("phase") != "DAILY_SAME_SCAN_REVIEW_V1":
        raise ValueError("daily_review_phase_mismatch")
    top = report.get("topFiveReviewCandidates")
    results = report.get("results")
    if not isinstance(top, list) or not isinstance(results, list):
        raise ValueError("daily_review_shape_invalid")
    by_game = {str(row.get("game") or ""): row for row in results if isinstance(row, dict)}
    items = []
    for rank, game in enumerate(top[:5], 1):
        game = str(game or "").strip()
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
        for detail in row.get("details") or []:
            if not isinstance(detail, dict) or detail.get("detailConfirmed") is not True:
                continue
            url = safe_https(detail.get("finalUrl"))
            sid = str(detail.get("source") or "").strip()
            if url and sid:
                point_sites.append({"source": sid, "url": url})
        dedup = {(x["source"], x["url"]): x for x in point_sites}
        if len({x[0] for x in dedup}) < 2:
            raise ValueError("ranked_game_confirmed_sources_below_two")
        items.append({
            "rank": rank,
            "game": game,
            "maxObservedRewardYen": amount,
            "confirmedSourceCount": int(row.get("confirmedSourceCount") or 0),
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
        "count": len(items),
        "items": items,
    }


def write(input_path=INPUT, output_path=OUTPUT):
    out = build(load(input_path))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return out


def main():
    out = write()
    print(json.dumps({"phase": out["phase"], "count": out["count"], "publicationAuthorized": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
