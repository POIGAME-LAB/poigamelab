"""Validate actual CSV/artifact output before any remote publication (no API)."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import direct_offer_refresh as direct

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate(root, baseline, artifact):
    rows = read_csv(root / "data/published_offers.csv")
    old = read_csv(baseline)
    games = {g["name"] for g in read_csv(root / "games.csv")}
    sources = {s["id"]: s for s in json.loads((root / "config/point_sources.json").read_text())["sources"]}
    errors = []
    by_key = {}
    for row in rows:
        key = row.get("offerKey")
        if not key or key in by_key:
            errors.append("missing_or_duplicate_offer_key")
        by_key[key] = row
        if row.get("game") not in games:
            errors.append("unknown_catalog_game")
        if not str(row.get("reward", "")).isdigit() or int(row["reward"]) <= 0:
            errors.append("invalid_reward")
        if row.get("verified") != "true" or not row.get("condition"):
            errors.append("unverified_or_missing_condition")
        source = sources.get(row.get("site"))
        if not source or not all(direct.source_host_allowed(row.get(k), source) for k in ("url", "sourceUrl")):
            errors.append("invalid_source_url")
    for row in old:
        current = by_key.get(row.get("offerKey"))
        if current is None:
            errors.append("existing_offer_removed")
        elif any(current.get(k) != row.get(k) for k in ("game", "site", "platform", "url", "offerKey")):
            errors.append("existing_offer_identity_changed")
    # Verify the data actually uploaded to Pages, not just a mock fetch response.
    for path in ("games.csv", "data/published_offers.csv", "config/refresh_policy.json"):
        target = artifact / path
        if not target.is_file() or target.read_bytes() != (root / path).read_bytes():
            errors.append("artifact_data_missing_or_stale:" + path)
    for path in ("index.html", "offers.html", "game.html", "guides.html", "site-data.js"):
        if not (artifact / path).is_file():
            errors.append("artifact_page_missing:" + path)
    for name in ("daily_scan_review.json", "comparison_review_queue.json", "new_game_candidate_history.json"):
        if (artifact / "data" / name).exists():
            errors.append("private_research_in_public_artifact:" + name)
    if errors:
        raise ValueError(";".join(sorted(set(errors))))
    return {"valid": True, "publishedRows": len(rows), "preservedOfferIdentities": len(old), "apiCalls": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    print(json.dumps(validate(ROOT, args.baseline, args.artifact)))


if __name__ == "__main__":
    main()
