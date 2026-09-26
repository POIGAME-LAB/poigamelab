#!/usr/bin/env python3
"""Upsert strictly authorized Point Income device-detail offers into publication data.

This never publishes candidate-only/downstream-authoritative rows and never
removes last-known-good Point Income rows merely because a device capture failed
or an offer was not part of the reviewed detail sample.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
]
SITE = "point_income"
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_PATH_RE = re.compile(r"^/ad/([0-9]+)/?$")


def jst_date():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()


def canonical_url(value):
    try:
        parsed = urlparse(str(value or "").strip())
        port = parsed.port
    except (TypeError, ValueError):
        return ""
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        return ""
    match = AD_PATH_RE.fullmatch(parsed.path or "")
    return f"https://sp.pointi.jp/ad/{match.group(1)}/" if match else ""


def row_from_item(item, updated_at):
    if not isinstance(item, dict):
        return None
    if item.get("state") != "parsed" or item.get("publicationAuthorized") is not True:
        return None
    if item.get("downstreamTermsRequired") is not False or item.get("candidateOnly") is not False:
        return None
    game = str(item.get("game") or "").strip()
    platform = str(item.get("platform") or "").strip()
    url = canonical_url(item.get("url"))
    condition = re.sub(r"\s+", " ", str(item.get("conditionText") or "")).strip()
    deadline = re.sub(r"\s+", " ", str(item.get("deadline") or "")).strip()
    reward = item.get("verifiedCurrentRewardYen")
    if not game or platform not in {"iOS", "Android"} or not url:
        return None
    if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not 0 < reward <= 5_000_000:
        return None
    if not condition or len(condition) > 2000 or not deadline or len(deadline) > 300:
        return None
    offer_key = f"{game}|{SITE}|{platform}|{url}"
    return {
        "offerKey": offer_key,
        "game": game,
        "site": SITE,
        "provider": "",
        "reward": str(int(reward)) if float(reward).is_integer() else ("%.1f" % reward).rstrip("0").rstrip("."),
        "condition": condition,
        "platform": platform,
        "type": "通常",
        "deadline": deadline,
        "updatedAt": updated_at,
        "url": url,
        "sourceUrl": url,
        "verified": "true",
    }


def publish(review, published_path, updated_at=None):
    if not isinstance(review, dict) or review.get("phase") != "POINT_INCOME_DEVICE_DETAIL_REVIEW_V1":
        raise ValueError("unexpected_review_payload")
    items = review.get("items")
    if not isinstance(items, list):
        raise ValueError("invalid_review_payload")
    updated_at = updated_at or jst_date()
    fresh = []
    seen = set()
    for item in items:
        row = row_from_item(item, updated_at)
        if not row or row["offerKey"] in seen:
            continue
        seen.add(row["offerKey"])
        fresh.append(row)

    path = Path(published_path)
    old_rows = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            old_rows = list(csv.DictReader(f))

    merged = {}
    for row in old_rows:
        key = str(row.get("offerKey") or "").strip()
        if key:
            merged[key] = {field: str(row.get(field) or "") for field in FIELDS}
    for row in fresh:
        merged[row["offerKey"]] = {field: row[field] for field in FIELDS}

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])
    tmp.replace(path)
    return fresh


def main(review_path, published_path):
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    rows = publish(review, Path(published_path))
    print(json.dumps({"publishedPointIncomeRows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: publish-point-income-device-offers.py REVIEW PUBLISHED_CSV")
    main(sys.argv[1], sys.argv[2])
