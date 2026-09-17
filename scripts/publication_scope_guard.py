#!/usr/bin/env python3
"""Keep stale/unrefreshable offer rows as history without publishing them as current.

This guard performs no network requests and never re-activates an offer. It only
changes verified=true to verified=false when a row's source is outside the
policy's currentPriceSources contract. All identity, reward, condition, URL and
history fields are preserved.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "refresh_policy.json"
PUBLISHED = ROOT / "data" / "published_offers.csv"


def _current_price_sources(policy_path: Path):
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    unified = policy.get("unifiedDailySources")
    current = (policy.get("publication") or {}).get("currentPriceSources")
    if not isinstance(unified, list) or not isinstance(current, list) or not current:
        raise ValueError("current_price_source_policy_missing")
    if any(not isinstance(value, str) or not value.strip() for value in current):
        raise ValueError("invalid_current_price_source")
    normalized = [value.strip() for value in current]
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate_current_price_source")
    if not set(normalized).issubset({str(value).strip() for value in unified}):
        raise ValueError("current_price_source_outside_unified_daily_sources")
    return set(normalized)


def enforce_scope(published_path=PUBLISHED, policy_path=POLICY):
    published_path = Path(published_path)
    current_sources = _current_price_sources(Path(policy_path))
    if not published_path.exists():
        raise ValueError("published_offers_missing")

    with published_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    required = {"offerKey", "site", "verified"}
    if not required.issubset(fieldnames):
        raise ValueError("published_offer_schema_invalid")

    deactivated = []
    for row in rows:
        site = str(row.get("site") or "").strip()
        verified = str(row.get("verified") or "").strip().lower()
        if verified not in {"true", "false"}:
            raise ValueError("invalid_verified_flag")
        if verified == "true" and site not in current_sources:
            row["verified"] = "false"
            deactivated.append(str(row.get("offerKey") or ""))

    if deactivated:
        temporary = published_path.with_suffix(published_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(published_path)

    return {
        "mode": "deactivate-only",
        "currentPriceSources": sorted(current_sources),
        "deactivatedRows": len(deactivated),
        "deactivatedOfferKeys": deactivated,
        "networkCalls": 0,
        "reactivatedRows": 0,
        "deletedRows": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deactivate out-of-scope current-price rows without deleting history.")
    parser.add_argument("--published", type=Path, default=PUBLISHED)
    parser.add_argument("--policy", type=Path, default=POLICY)
    args = parser.parse_args(argv)
    try:
        result = enforce_scope(args.published, args.policy)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"phase": "PUBLICATION_SCOPE_GUARD_V1", "success": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"phase": "PUBLICATION_SCOPE_GUARD_V1", "success": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
