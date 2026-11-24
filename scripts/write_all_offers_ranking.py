#!/usr/bin/env python3
"""Write data/all_offers_ranking.json from today's private daily review (no network, no API).

Every new-game offer seen on today's first-party listings, ranked by its listing amount, so the
daily-guide routine and the operator can see the whole field - not only the top-five handoff
(which needs two sites and a complete scan). Candidate-only: nothing here is published.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(review: dict) -> dict:
    summary = review.get("allOffers")
    if not isinstance(summary, dict) or not isinstance(summary.get("games"), list):
        raise ValueError("all_offers_missing")
    return {
        "schemaVersion": 1,
        "phase": "ALL_OFFERS_RANKING_V1",
        "checkedAt": review.get("checkedAt"),
        "candidateOnly": True,
        "publicationAuthorized": False,
        "amountNote": "listingUpperBoundYen は各ポイントサイトの一覧に出ている額（上限・未確認）。"
                      "verifiedRewardYen は当日に公式の案件ページで確認できた額。どちらも公開データではない。",
        "rankingCompleteForTopFive": review.get("rankingComplete"),
        "incompleteDiscoverySources": review.get("incompleteDiscoverySources") or [],
        "gameCount": summary.get("gameCount"),
        "offerCount": summary.get("offerCount"),
        "offersBySource": summary.get("offersBySource") or {},
        "games": summary["games"],
    }


def main(argv=None) -> int:
    review_path = ROOT / "data/daily_scan_review.json"
    out_path = ROOT / "data/all_offers_ranking.json"
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        out = build(review)
    except (OSError, ValueError) as error:  # never block the daily refresh over this summary
        print(f"WARN: all offers ranking not written: {type(error).__name__}: {error}")
        return 0
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"all offers ranking: games={out['gameCount']} offers={out['offerCount']} by_source={out['offersBySource']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
