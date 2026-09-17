#!/usr/bin/env python3
"""Promote safe Moppy reward-only evidence from the shared nightly crawl.

No network access is performed here. The script consumes the current run's
review queue, updates only already-published Moppy rows whose exact first-party
offer identity is unique, and preserves condition/deadline/type prose.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published_offers.csv"
REVIEW = ROOT / "data" / "comparison_review_queue.json"
STATUS = ROOT / "data" / "comparison_refresh_status.json"
DAILY = ROOT / "data" / "daily_scan_review.json"
SNAPSHOT = ROOT / "data" / "unified_offer_snapshot.json"

MOPPY_PARSER = "moppy-shell-review-v1"
MOPPY_HOST = "pc.moppy.jp"
FINGERPRINT_FIELDS = (
    "offerId",
    "name",
    "platform",
    "displayedRewardPoints",
    "rewardUnit",
    "baseYenPerPoint",
    "downstreamTermsRequired",
    "headerText",
    "termsText",
)


def _load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError, TypeError):
        return default


def _atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _offer_id(url):
    try:
        parsed = urlparse(str(url or ""))
        if (
            parsed.scheme != "https"
            or parsed.hostname != MOPPY_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.path != "/ad/detail.php"
            or parsed.fragment
        ):
            return ""
        query = parse_qs(parsed.query, keep_blank_values=True)
    except (TypeError, ValueError):
        return ""
    allowed = {"site_id", "s_id"}
    if any(key not in allowed for key in query):
        return ""
    values = []
    for key in ("site_id", "s_id"):
        items = query.get(key, [])
        if len(items) > 1:
            return ""
        if items:
            values.append(items[0])
    if len(values) != 1 or not values[0].isdigit():
        return ""
    return values[0]


def _fingerprint(evidence):
    if not all(field in evidence for field in FINGERPRINT_FIELDS):
        return ""
    payload = {field: evidence[field] for field in FINGERPRINT_FIELDS}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _jst_date(checked_at):
    try:
        value = datetime.fromisoformat(str(checked_at))
    except ValueError:
        return ""
    if value.tzinfo is None:
        return ""
    return value.astimezone(timezone(timedelta(hours=9))).date().isoformat()


def _evidence_candidate(item, checked_at):
    if not isinstance(item, dict):
        return None
    if item.get("source") != "moppy":
        return None
    if item.get("approvalHoldReason") != "source_refresh_not_enabled":
        return None
    if item.get("checkedAt") != checked_at:
        return None
    evidence = item.get("sourceEvidence")
    if not isinstance(evidence, dict):
        return None
    if evidence.get("state") != "parsed" or evidence.get("parserVersion") != MOPPY_PARSER:
        return None
    if evidence.get("evidenceFingerprint") != _fingerprint(evidence):
        return None
    if evidence.get("rewardUnit") != "P" or evidence.get("baseYenPerPoint") != 1:
        return None
    if evidence.get("downstreamTermsRequired") is not True:
        return None
    reward = evidence.get("displayedRewardPoints")
    if type(reward) is not int or not (0 < reward < 1_000_000):
        return None
    platform = evidence.get("platform")
    if platform not in {"iOS", "Android"}:
        return None
    item_id = _offer_id(item.get("url"))
    if not item_id or item_id != str(evidence.get("offerId") or ""):
        return None
    stored_reward = str(item.get("storedReward") or "").replace(",", "")
    if not stored_reward.isdigit():
        return None
    stored_platform = str(item.get("storedPlatform") or "")
    return {
        "game": str(item.get("game") or ""),
        "offerId": item_id,
        "url": str(item.get("url") or ""),
        "reward": reward,
        "platform": platform,
        "storedReward": stored_reward,
        "storedPlatform": stored_platform,
        "parserVersion": MOPPY_PARSER,
    }


def _refresh_snapshot(snapshot, promoted):
    if not isinstance(snapshot, dict):
        return
    changed = {}
    for key, candidate in promoted.items():
        changed[(candidate["game"], candidate["offerId"])] = candidate

    for group in snapshot.get("groups") or []:
        if not isinstance(group, dict):
            continue
        for offer in group.get("offers") or []:
            if not isinstance(offer, dict) or offer.get("source") != "moppy":
                continue
            candidate = changed.get((str(group.get("game") or ""), _offer_id(offer.get("url"))))
            if candidate is None:
                continue
            offer["rewardYen"] = candidate["reward"]
            offer["rewardVerified"] = True
            offer["parserVersion"] = MOPPY_PARSER
        rewards = [
            offer.get("rewardYen")
            for offer in (group.get("offers") or [])
            if isinstance(offer, dict) and type(offer.get("rewardYen")) is int
        ]
        group["verifiedRewardCount"] = len(rewards)
        group["maxVerifiedRewardYen"] = max(rewards) if rewards else None


def main():
    if not PUBLISHED.exists():
        print("ERROR: published_offers.csv is missing")
        return 2

    status = _load_json(STATUS, {})
    checked_at = str(status.get("checkedAt") or "")
    checked_date = _jst_date(checked_at)
    if not checked_at or not checked_date:
        print("ERROR: current refresh checkedAt is missing or invalid")
        return 2

    review = _load_json(REVIEW, {})
    items = review.get("items") if isinstance(review, dict) else None
    if not isinstance(items, list):
        print("ERROR: comparison review queue is missing or invalid")
        return 2

    with PUBLISHED.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    if not fieldnames or "offerKey" not in fieldnames:
        print("ERROR: published offer CSV schema is invalid")
        return 2

    by_identity = {}
    for index, row in enumerate(rows):
        if row.get("site") != "moppy":
            continue
        oid = _offer_id(row.get("url"))
        if oid:
            by_identity.setdefault(oid, []).append(index)

    candidates = {}
    invalid_items = 0
    for item in items:
        if not isinstance(item, dict) or item.get("source") != "moppy":
            continue
        candidate = _evidence_candidate(item, checked_at)
        if candidate is None:
            invalid_items += 1
            continue
        key = candidate["offerId"]
        candidates.setdefault(key, []).append(candidate)

    promoted = {}
    verified_rows = 0
    reward_changes = 0
    held = invalid_items

    for offer_id, evidence_rows in candidates.items():
        row_indexes = by_identity.get(offer_id, [])
        if len(evidence_rows) != 1 or len(row_indexes) != 1:
            held += len(evidence_rows)
            continue
        candidate = evidence_rows[0]
        row = rows[row_indexes[0]]
        if str(row.get("game") or "") != candidate["game"]:
            held += 1
            continue
        row_reward = str(row.get("reward") or "").replace(",", "")
        if (
            row.get("verified") != "true"
            or not row_reward.isdigit()
            or row_reward != candidate["storedReward"]
            or str(row.get("platform") or "") != candidate["storedPlatform"]
            or _offer_id(row.get("url")) != candidate["offerId"]
        ):
            held += 1
            continue
        stored_platform = candidate["storedPlatform"]
        if stored_platform not in {"", "不明", candidate["platform"]}:
            held += 1
            continue

        if int(row_reward) != candidate["reward"]:
            row["reward"] = str(candidate["reward"])
            reward_changes += 1
        row["updatedAt"] = checked_date
        row["sourceUrl"] = candidate["url"]
        row["verified"] = "true"
        promoted[(candidate["game"], candidate["offerId"])] = candidate
        verified_rows += 1

    if promoted:
        temporary = PUBLISHED.with_suffix(".csv.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(PUBLISHED)

    summary = {
        "mode": "existing-row-reward-only",
        "checkedAt": checked_at,
        "verifiedRows": verified_rows,
        "rewardChanges": reward_changes,
        "heldItems": held,
        "networkCalls": 0,
        "conditionsChanged": 0,
        "newRowsCreated": 0,
    }

    status["moppyRewardOnly"] = summary
    status["publishedRewardChanges"] = int(status.get("publishedRewardChanges") or 0) + reward_changes
    status["refreshedRows"] = int(status.get("refreshedRows") or 0) + verified_rows
    _atomic_json(STATUS, status)

    daily = _load_json(DAILY, {})
    if isinstance(daily, dict):
        daily["moppyRewardOnlyPublication"] = summary
        _atomic_json(DAILY, daily)

    if SNAPSHOT.exists():
        snapshot = _load_json(SNAPSHOT, {})
        _refresh_snapshot(snapshot, promoted)
        _atomic_json(SNAPSHOT, snapshot)

    print(json.dumps({"phase": "MOPPY_REWARD_ONLY_REFRESH_V1", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
