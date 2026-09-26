#!/usr/bin/env python3
"""Refresh rewards for already-verified Point Income rows from listing-only evidence.

This is deliberately narrow: it may update only an existing published
Point Income row whose exact /ad/<id>/ identity, game alias, and platform still
match the current residential-device catalog. It never creates new publication
rows and never deletes last-known-good rows.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIASES = ROOT / "config" / "point_income_game_aliases.json"
FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
]
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_PATH_RE = re.compile(r"^/ad/([0-9]+)/?$")


def jst_date():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()


def game_key(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"【[^】]*】", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[（(](?:ios|android|iphone)用[）)]", " ", text, flags=re.I)
    text = text.replace("＆", "&")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[・･·／/｜|：:‐‑‒–—―_\-]+", "", text)
    text = re.sub(r"[【】\[\]（）()「」『』〈〉《》]", "", text)
    return text[:320]


def load_aliases(path=DEFAULT_ALIASES):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("invalid_alias_registry")
    out = {}
    for row in data.get("games") or []:
        game = str(row.get("game") or "").strip()
        aliases = row.get("aliases") or []
        keys = []
        for value in [game] + list(aliases):
            key = game_key(value)
            if key and key not in keys:
                keys.append(key)
        if game and keys:
            out[game] = keys
    return out


def ad_id_from_url(value):
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
    return match.group(1) if match else ""


def aliases_match(game, title, aliases):
    title_key = game_key(title)
    return bool(title_key) and any(key and key in title_key for key in aliases.get(game, []))


def refresh(catalog, published_path, aliases_path=DEFAULT_ALIASES, updated_at=None):
    if not isinstance(catalog, dict) or catalog.get("source") != "point_income":
        raise ValueError("unexpected_source")
    if catalog.get("pointRate") != "10pt=1JPY":
        raise ValueError("point_rate_contract_mismatch")
    offers = catalog.get("offers")
    if not isinstance(offers, list):
        raise ValueError("invalid_catalog")

    by_id = {}
    for item in offers:
        if not isinstance(item, dict):
            continue
        ad_id = str(item.get("adId") or "").strip()
        url_id = ad_id_from_url(item.get("url"))
        title = str(item.get("title") or "").strip()
        platform = str(item.get("platform") or "").strip()
        points = item.get("currentPoints")
        if (
            not ad_id
            or url_id != ad_id
            or not title
            or platform not in {"iOS", "Android"}
            or type(points) is not int
            or not 0 < points <= 10_000_000
        ):
            continue
        by_id[ad_id] = item

    aliases = load_aliases(aliases_path)
    path = Path(published_path)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("published_offers_empty")

    changed = []
    updated_at = updated_at or jst_date()
    for row in rows:
        if str(row.get("site") or "") != "point_income":
            continue
        if str(row.get("verified") or "").strip().casefold() != "true":
            continue
        ad_id = ad_id_from_url(row.get("sourceUrl") or row.get("url"))
        offer = by_id.get(ad_id)
        if not offer:
            continue
        game = str(row.get("game") or "").strip()
        platform = str(row.get("platform") or "").strip()
        if game not in aliases:
            continue
        if offer.get("platform") != platform:
            continue
        if not aliases_match(game, offer.get("title"), aliases):
            continue
        points = offer.get("currentPoints")
        if points % 10 != 0:
            # Published reward contract is integer JPY. Keep LKG on fractional JPY.
            continue
        reward = str(points // 10)
        if str(row.get("reward") or "").strip() == reward:
            continue
        row["reward"] = reward
        row["updatedAt"] = updated_at
        changed.append({
            "game": game,
            "platform": platform,
            "adId": ad_id,
            "reward": reward,
        })

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field) or "") for field in FIELDS})
    tmp.replace(path)
    return changed


def main(catalog_path, published_path, aliases_path=DEFAULT_ALIASES):
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    changed = refresh(catalog, Path(published_path), aliases_path)
    print(json.dumps({
        "refreshedExistingPointIncomeRows": len(changed),
        "changes": changed,
    }, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(
            "usage: refresh-point-income-listing-only.py CATALOG PUBLISHED_CSV [ALIASES]"
        )
    main(
        sys.argv[1],
        sys.argv[2],
        Path(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_ALIASES,
    )
