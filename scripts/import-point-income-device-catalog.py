#!/usr/bin/env python3
"""Validate a residential-device supplied Point Income public offer catalog."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_OFFERS = 2000
MAX_DETAIL_EVIDENCE = 100
MAX_HEADINGS = 30
MAX_SNIPPETS = 6
AD_RE = re.compile(r"^/ad/(\d+)/?$")
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



def first_party_ad_url(value, expected_ad_id=""):
    text = str(value or "").strip()
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in ALLOWED_HOSTS
        or parsed.query
        or parsed.fragment
    ):
        return ""
    match = AD_RE.fullmatch(parsed.path or "")
    if not match:
        return ""
    ad_id = match.group(1)
    if expected_ad_id and ad_id != expected_ad_id:
        return ""
    return f"https://sp.pointi.jp/ad/{ad_id}/"


def clean_public_text(value, max_len):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_len:
        return ""
    lowered = text.casefold()
    if (
        "<script" in lowered
        or "<html" in lowered
        or "github_pat_" in lowered
        or re.search(r"\bghp_[a-z0-9_]{20,}\b", lowered)
    ):
        return ""
    return text


def validate_detail_evidence(item, offers_by_id):
    if not isinstance(item, dict):
        return None
    ad_id = normalize_ad_id(item.get("adId") or item.get("url"))
    offer = offers_by_id.get(ad_id)
    if not offer:
        return None

    url = first_party_ad_url(item.get("url"), ad_id)
    final_url = first_party_ad_url(item.get("finalUrl") or item.get("url"), ad_id)
    if not url or not final_url:
        return None

    state = str(item.get("state") or "captured").strip()
    if state not in {"captured", "review_required"}:
        return None

    game_hint = clean_public_text(item.get("gameHint"), 120)
    if not game_hint:
        return None

    base = {
        "evidenceVersion": 1,
        "adId": ad_id,
        "gameHint": game_hint,
        "url": url,
        "finalUrl": final_url,
        "listingTitle": offer.get("title", ""),
        "listingPlatform": offer.get("platform", ""),
        "listingCurrentPoints": offer.get("currentPoints"),
        "candidateOnly": True,
        "publicationAuthorized": False,
    }
    if state == "review_required":
        base["state"] = "review_required"
        base["reason"] = "detail_fetch_or_parse_failed"
        return base

    page_title = clean_public_text(item.get("pageTitle"), 500)
    meta_description = clean_public_text(item.get("metaDescription"), 1000)
    lead_text = clean_public_text(item.get("leadText"), 2600)
    headings_raw = item.get("headings")
    snippets_raw = item.get("keywordSnippets")
    if not isinstance(headings_raw, list) or not isinstance(snippets_raw, list):
        return None
    if len(headings_raw) > MAX_HEADINGS or len(snippets_raw) > MAX_SNIPPETS:
        return None

    headings = []
    for value in headings_raw:
        cleaned = clean_public_text(value, 260)
        if not cleaned:
            continue
        if cleaned not in headings:
            headings.append(cleaned)

    snippets = []
    for value in snippets_raw:
        cleaned = clean_public_text(value, 2000)
        if not cleaned:
            continue
        if cleaned not in snippets:
            snippets.append(cleaned)

    text_length = item.get("textLength")
    if type(text_length) is not int or not 0 <= text_length <= 1_000_000:
        return None
    if not any((page_title, meta_description, lead_text, headings, snippets)):
        return None

    canonical_url = ""
    if item.get("canonicalUrl"):
        canonical_url = first_party_ad_url(item.get("canonicalUrl"), ad_id)
        if not canonical_url:
            return None

    base.update({
        "state": "captured",
        "canonicalUrl": canonical_url,
        "pageTitle": page_title,
        "metaDescription": meta_description,
        "headings": headings,
        "leadText": lead_text,
        "keywordSnippets": snippets,
        "textLength": text_length,
    })
    return base

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

    offers_by_id = {item["adId"]: item for item in offers}
    detail_evidence = []
    raw_detail_evidence = data.get("detailEvidence")
    if raw_detail_evidence is not None:
        if not isinstance(raw_detail_evidence, list):
            raise SystemExit("detailEvidence must be a list")
        if len(raw_detail_evidence) > MAX_DETAIL_EVIDENCE:
            raise SystemExit("refusing implausibly large detailEvidence")
        seen_detail = set()
        for raw in raw_detail_evidence:
            item = validate_detail_evidence(raw, offers_by_id)
            if item and item["adId"] not in seen_detail:
                seen_detail.add(item["adId"])
                detail_evidence.append(item)

    result = {
        "schemaVersion": 3 if detail_evidence else 2,
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
        "detailEvidence": detail_evidence,
        "detailEvidenceCount": len(detail_evidence),
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "accepted": True,
        "count": len(offers),
        "detailEvidenceCount": len(detail_evidence),
    }))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
