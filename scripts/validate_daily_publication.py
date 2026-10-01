"""Validate actual CSV/artifact output before any remote publication (no API)."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import direct_offer_refresh as direct
from structured_publication import published_row_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def reviewed_retirement_keys(root):
    """Return only exact offer keys retired by the audited publication contract."""
    try:
        report = json.loads(
            (Path(root) / "data/daily_scan_review.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()
    publication = report.get("existingPublication") or {}
    decisions = publication.get("decisions") or []
    return {
        str(decision.get("offerKey") or "")
        for decision in decisions
        if (
            (
                (decision.get("source") == "hapitas"
                 and decision.get("publicationMode") == "explicit_unavailable_retirement")
                or (decision.get("source") in {"warau", "hapitas"}
                    and decision.get("publicationMode") == "confirmed_unavailable_retirement"
                    and type(decision.get("consecutiveUnavailableRuns")) is int
                    and decision["consecutiveUnavailableRuns"] >= 3)
            )
            and decision.get("retired") is True
            and decision.get("updated") is True
            and not decision.get("holdReason")
            and str(decision.get("offerKey") or "")
        )
    }


def validate(root, baseline, artifact):
    rows = read_csv(root / "data/published_offers.csv")
    old = read_csv(baseline)
    allowed_retirements = reviewed_retirement_keys(root)
    games = {g["name"] for g in read_csv(root / "games.csv")}
    sources = {s["id"]: s for s in json.loads((root / "config/point_sources.json").read_text())["sources"]}
    errors = []
    by_key = {}
    old_keys = {row.get("offerKey") for row in old}
    try:
        report = json.loads((root / "data/daily_scan_review.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    addition_decisions = (report.get("existingPublication") or {}).get("decisions", [])
    for row in rows:
        key = row.get("offerKey")
        if not key or key in by_key:
            errors.append("missing_or_duplicate_offer_key")
        by_key[key] = row
        if key not in old_keys:
            matches = [d for d in addition_decisions if d.get("offerKey") == key]
            if not (len(matches) == 1 and matches[0].get("added") is True
                    and matches[0].get("publicationMode") == "verified_existing_game"
                    and matches[0].get("publicationEligible") is True
                    and not matches[0].get("holdReason")
                    and matches[0].get("rowFingerprint") == published_row_fingerprint(row)):
                errors.append("new_offer_without_verified_gate_decision")
            if row.get("platform") not in {"iOS", "Android"} or not row.get("deadline"):
                errors.append("new_offer_missing_platform_or_deadline")
        if row.get("game") not in games:
            errors.append("unknown_catalog_game")
        if not str(row.get("reward", "")).isdigit() or int(row["reward"]) <= 0:
            errors.append("invalid_reward")
        if row.get("verified") != "true" or not row.get("condition"):
            errors.append("unverified_or_missing_condition")
        source = sources.get(row.get("site"))
        if not source or not all(direct.source_host_allowed(row.get(k), source) for k in ("url", "sourceUrl")):
            errors.append("invalid_source_url")
    retired = []
    for row in old:
        offer_key = row.get("offerKey")
        current = by_key.get(offer_key)
        if current is None:
            if offer_key in allowed_retirements:
                retired.append(offer_key)
            else:
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
    return {
        "valid": True,
        "publishedRows": len(rows),
        "preservedOfferIdentities": len(old) - len(retired),
        "retiredOfferIdentities": len(retired),
        "apiCalls": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    print(json.dumps(validate(ROOT, args.baseline, args.artifact)))


if __name__ == "__main__":
    main()
