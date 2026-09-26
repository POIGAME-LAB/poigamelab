#!/usr/bin/env python3
"""Strictly verify sanitized Point Income iPhone detail evidence.

The residential iPhone is only the transport needed to reach Point Income from
Japan. Publication decisions remain deterministic and fail closed in GitHub
Actions. Public shell offers whose own terms delegate reward/conditions to a
later destination remain review-only.
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIASES = ROOT / "config" / "point_income_game_aliases.json"
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_PATH_RE = re.compile(r"^/ad/([0-9]+)/?$")
PLATFORMS = {"iOS", "Android"}
REWARD_RE = re.compile(
    r"(?:(?P<old>[1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt\s*⇒\s*)?"
    r"(?P<current>[1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt\s*"
    r"\(\s*(?P<yen>[1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*円分\s*\)",
    re.I,
)
CONDITION_RE = re.compile(
    r"成果条件\s+詳細\s+成果条件\s+(.+?)\s+ポイント獲得条件",
    re.S,
)
DOWNSTREAM_PATTERNS = (
    r"遷移先ページに記載の条件達成",
    r"詳細は遷移先ページをご確認",
    r"本ページに記載のポイント数と、?\s*遷移先ページに記載されているポイント数が異なる",
    r"遷移先ページに記載のポイント数が適用",
    r"その他詳細は遷移先ページ",
    r"遷移先ページ[「『].{0,80}(?:マルチステージアプリ|アプリ利用でポイントGET!?).{0,80}[」』]内の条件",
)


def normalize_space(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
    rows = data.get("games")
    if not isinstance(rows, list):
        raise ValueError("invalid_alias_registry")
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_alias_registry")
        game = str(row.get("game") or "").strip()
        aliases = row.get("aliases")
        if not game or not isinstance(aliases, list):
            raise ValueError("invalid_alias_registry")
        keys = []
        for value in [game] + aliases:
            key = game_key(value)
            if key and key not in keys:
                keys.append(key)
        if not keys:
            raise ValueError("invalid_alias_registry")
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


def platform_from_title(title):
    ios = bool(re.search(r"(?:iOS|iPhone)\s*用", str(title or ""), re.I))
    android = bool(re.search(r"Android\s*用", str(title or ""), re.I))
    if ios and not android:
        return "iOS"
    if android and not ios:
        return "Android"
    return ""


def aliases_match(game, title, alias_registry):
    keys = alias_registry.get(game) or []
    title_key = game_key(title)
    return bool(title_key) and any(key and key in title_key for key in keys)


def parse_reward_header(lead_text):
    header = str(lead_text or "")
    cuts = [x for token in ("紹介する", "紹介用URL", "成果条件") if (x := header.find(token)) >= 0]
    if cuts:
        header = header[:min(cuts)]
    matches = []
    for m in REWARD_RE.finditer(header):
        old = int(m.group("old").replace(",", "")) if m.group("old") else None
        current = int(m.group("current").replace(",", ""))
        yen = int(m.group("yen").replace(",", ""))
        matches.append((old, current, yen))
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError("missing_or_ambiguous_displayed_reward")
    return unique[0]


def extract_condition_and_terms(lead_text):
    text = normalize_space(lead_text)
    match = CONDITION_RE.search(text)
    if not match:
        raise ValueError("missing_offer_condition")
    condition = normalize_space(match.group(1))
    if not 8 <= len(condition) <= 1000:
        raise ValueError("invalid_offer_condition")

    terms_start = match.end() - len("ポイント獲得条件")
    contact_start = text.find("ポイントに関するお問い合わせについて", terms_start)
    if contact_start < 0:
        raise ValueError("missing_terms_boundary")
    terms = normalize_space(text[terms_start:contact_start])
    if len(terms) < 250:
        raise ValueError("incomplete_offer_terms")
    if "対象外" not in terms:
        raise ValueError("incomplete_offer_terms")
    return condition, terms


def has_support_contract(detail):
    chunks = [
        str(detail.get("leadText") or ""),
        *[str(x or "") for x in (detail.get("keywordSnippets") or [])],
    ]
    text = " ".join(chunks)
    return (
        "ポイントインカムサポートセンター" in text
        and "広告主へ直接お問い合わせすることは禁止" in text
    )


def downstream_terms_required(condition, terms):
    text = normalize_space(condition + " " + terms)
    return any(re.search(pattern, text) for pattern in DOWNSTREAM_PATTERNS)


def deadline_from_condition(condition):
    text = normalize_space(condition)
    matches = re.findall(
        r"((?:承認待ち反映後、?|インストール(?:後|日から起算して)?、?|広告クリック(?:当日を1日目として)?、?)?\s*[0-9]{1,3}\s*日以内)",
        text,
    )
    cleaned = [normalize_space(x) for x in matches if normalize_space(x)]
    return cleaned[0] if cleaned else "条件欄の期限を参照"


def review_item(detail, offers_by_id, alias_registry):
    ad_id = str(detail.get("adId") or "").strip()
    game = str(detail.get("gameHint") or "").strip()
    offer = offers_by_id.get(ad_id)
    base = {
        "adId": ad_id,
        "game": game,
        "state": "review_required",
        "candidateOnly": True,
        "publicationAuthorized": False,
    }
    try:
        if not ad_id or not offer:
            raise ValueError("listing_identity_missing")
        if str(detail.get("state") or "captured") != "captured":
            raise ValueError(str(detail.get("reason") or "detail_not_captured"))
        if ad_id_from_url(detail.get("url")) != ad_id or ad_id_from_url(detail.get("finalUrl")) != ad_id:
            raise ValueError("detail_identity_mismatch")
        canonical = str(detail.get("canonicalUrl") or "").strip()
        if canonical and ad_id_from_url(canonical) != ad_id:
            raise ValueError("canonical_identity_mismatch")

        title = normalize_space(offer.get("title"))
        listing_title = normalize_space(detail.get("listingTitle"))
        headings = [normalize_space(x) for x in (detail.get("headings") or []) if normalize_space(x)]
        page_title = normalize_space(detail.get("pageTitle"))
        if not title or listing_title != title:
            raise ValueError("listing_title_mismatch")
        if title not in headings:
            raise ValueError("detail_heading_mismatch")
        if title not in page_title:
            raise ValueError("detail_page_title_mismatch")
        if game not in alias_registry or not aliases_match(game, title, alias_registry):
            raise ValueError("reviewed_game_alias_mismatch")

        platform = str(offer.get("platform") or "").strip()
        if platform not in PLATFORMS:
            raise ValueError("missing_offer_platform")
        if str(detail.get("listingPlatform") or "").strip() != platform:
            raise ValueError("listing_platform_mismatch")
        if platform_from_title(title) != platform:
            raise ValueError("title_platform_mismatch")

        points = offer.get("currentPoints")
        if type(points) is not int or not 0 < points <= 10_000_000:
            raise ValueError("invalid_listing_reward")
        if detail.get("listingCurrentPoints") != points:
            raise ValueError("listing_reward_mismatch")

        lead_text = normalize_space(detail.get("leadText"))
        if len(lead_text) < 800:
            raise ValueError("insufficient_detail_evidence")
        old_points, displayed_points, displayed_yen = parse_reward_header(lead_text)
        if displayed_points != points:
            raise ValueError("detail_reward_mismatch")
        if displayed_yen != math.floor(points / 10):
            raise ValueError("displayed_yen_mismatch")
        if old_points is not None and old_points >= displayed_points:
            raise ValueError("invalid_promotion_reward")

        condition, terms = extract_condition_and_terms(lead_text)
        if not has_support_contract(detail):
            raise ValueError("missing_point_income_support_contract")
        downstream = downstream_terms_required(condition, terms)
        normalized_yen = points / 10
        if normalized_yen.is_integer():
            normalized_yen = int(normalized_yen)

        payload = {
            "adId": ad_id,
            "game": game,
            "url": f"https://sp.pointi.jp/ad/{ad_id}/",
            "title": title,
            "platform": platform,
            "displayedCurrentRewardPoints": displayed_points,
            "displayedCurrentRewardYenFloor": displayed_yen,
            "verifiedCurrentRewardYen": normalized_yen,
            "rewardUnit": "Point-Income-pt",
            "sourcePointRate": "10pt=1JPY",
            "conditionText": condition,
            "deadline": deadline_from_condition(condition),
            "termsText": terms[:7000],
            "downstreamTermsRequired": downstream,
            "state": "parsed",
            "parserVersion": "point-income-device-detail-review-v1",
            "candidateOnly": downstream,
            "publicationAuthorized": not downstream,
        }
        if downstream:
            payload["reason"] = "downstream_terms_authoritative"
        return payload
    except (ValueError, TypeError, RecursionError) as error:
        base["reason"] = str(error)[:120]
        return base


def build_review(data, alias_registry):
    if not isinstance(data, dict) or data.get("source") != "point_income":
        raise ValueError("unexpected_source")
    if data.get("pointRate") != "10pt=1JPY":
        raise ValueError("point_rate_contract_mismatch")
    offers = data.get("offers")
    details = data.get("detailEvidence")
    if not isinstance(offers, list) or not isinstance(details, list):
        raise ValueError("invalid_device_catalog")
    offers_by_id = {
        str(x.get("adId") or ""): x
        for x in offers if isinstance(x, dict) and str(x.get("adId") or "")
    }
    items = [review_item(x, offers_by_id, alias_registry) for x in details if isinstance(x, dict)]
    return {
        "phase": "POINT_INCOME_DEVICE_DETAIL_REVIEW_V1",
        "source": "point_income",
        "pointRate": "10pt=1JPY",
        "count": len(items),
        "parsedCount": sum(x.get("state") == "parsed" for x in items),
        "publishableCount": sum(x.get("publicationAuthorized") is True for x in items),
        "downstreamRequiredCount": sum(x.get("downstreamTermsRequired") is True for x in items),
        "reviewRequiredCount": sum(x.get("state") == "review_required" for x in items),
        "items": items,
    }


def main(inp, out, aliases_path=DEFAULT_ALIASES):
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    aliases = load_aliases(aliases_path)
    result = build_review(data, aliases)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "parsedCount": result["parsedCount"],
        "publishableCount": result["publishableCount"],
        "downstreamRequiredCount": result["downstreamRequiredCount"],
        "reviewRequiredCount": result["reviewRequiredCount"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        raise SystemExit("usage: verify-point-income-device-details.py INPUT OUTPUT [ALIASES]")
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_ALIASES)
