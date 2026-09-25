#!/usr/bin/env python3
"""Validate a residential-device supplied Point Income public offer catalog."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_OFFERS = 2000
AD_RE = re.compile(r"^/ad/(\\d+)/?$")
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
PLATFORMS = {"", "iOS", "Android", "iOS|Android"}


def normalize_ad_id(value):
    text = str(value or "").strip()
    if text.isdigit():
        return text
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    if (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() in ALLOWED_HOSTS
        and not parsed.query
        and not parsed.fragment
    ):
        match = AD_RE.fullmatch(parsed.path or "")
        if match:
            return match.group(1)
    return ""


def yen_from_points(points):
    value = points / 10
    return int(value) if value.is_integer() else value


def validate_offer(item):
    if not isinstance(item, dict):
        return None
    ad_id = normalize_ad_id(item.get("adId") or item.get("url"))
    title = str(item.get("title") or "").strip()
    platform = str(item.get("platform") or "").strip()
    points = item.get("currentPoints")
    if not ad_id or not 2 <= len(title) <= 260:
        return None
    if platform not in PLATFORMS:
        return None
    if type(points) is not int or not 0 < points <= 10_000_000:
        return None
    return {
        "adId": ad_id,
        "url": f"https://sp.pointi.jp/ad/{ad_id}/",
        "title": title,
        "platform": platform,
        "currentPoints": points,
        "currentYen": yen_from_points(points),
        "rewardText": f"{points:,}pt",
        "candidateOnly": True,
        "publicationAuthorized": False,
    }


def main(inp, out):
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("payload must be an object")
    if data.get("source") not in {None, "point_income"}:
        raise SystemExit("unexpected source")

    source_url = str(data.get("sourceUrl") or "").strip()
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
            raise SystemExit("sourceUrl must be first-party Point Income https")

    raw_offers = data.get("offers")
    offers = []
    seen = set()
    if isinstance(raw_offers, list):
        for raw in raw_offers:
            item = validate_offer(raw)
            if item and item["adId"] not in seen:
                seen.add(item["adId"])
                offers.append(item)
    else:
        raw_ids = data.get("adIds")
        if raw_ids is None:
            raw_ids = data.get("adUrls")
        if isinstance(raw_ids, list):
            for value in raw_ids:
                ad_id = normalize_ad_id(value)
                if ad_id and ad_id not in seen:
                    seen.add(ad_id)
                    offers.append({
                        "adId": ad_id,
                        "url": f"https://sp.pointi.jp/ad/{ad_id}/",
                        "candidateOnly": True,
                        "publicationAuthorized": False,
                    })

    if not offers:
        raise SystemExit("refusing empty Point Income candidate catalog")
    if len(offers) > MAX_OFFERS:
        raise SystemExit("refusing implausibly large Point Income catalog")

    result = {
        "schemaVersion": 2,
        "source": "point_income",
        "scope": "residential_public_category_68_catalog",
        "candidateOnly": True,
        "catalogCompleteClaim": False,
        "sourceUrl": source_url,
        "pointRate": "10pt=1JPY",
        "pageCount": int(data.get("pageCount") or 0),
        "stoppedBecause": str(data.get("stoppedBecause") or ""),
        "offers": offers,
        "count": len(offers),
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"accepted": True, "count": len(offers)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
