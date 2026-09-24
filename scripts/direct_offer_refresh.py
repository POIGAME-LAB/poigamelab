#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import hashlib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "refresh_policy.json"
TARGETS = ROOT / "config" / "game_targets.json"
SOURCES = ROOT / "config" / "point_sources.json"
OFFERWALL_PROVIDERS = ROOT / "config" / "offerwall_providers.json"
PUBLISHED = ROOT / "data" / "published_offers.csv"
STATUS = ROOT / "data" / "comparison_refresh_status.json"
LEGACY_STATUS = ROOT / "data" / "refresh_status.json"
REVIEW = ROOT / "data" / "comparison_review_queue.json"
NEW_GAME_QUEUE = ROOT / "data" / "new_game_candidate_queue.json"
NEW_GAME_HISTORY = ROOT / "data" / "new_game_candidate_history.json"
EXISTING_GAME_QUEUE = ROOT / "data" / "existing_game_candidate_queue.json"

FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
]

DETAIL_QUERY_KEYS = {"point_id", "site_id", "s_id", "itemid", "campaign_id", "campaignid", "cd_client", "id"}

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def today_jst():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def source_host_allowed(url, source):
    try:
        parsed = urlparse(str(url or ""))
        port = parsed.port
    except (TypeError, ValueError):
        return False
    # Scheduled evidence collection is HTTPS-only. Reject credentials and
    # non-standard ports so a same-domain redirect cannot silently downgrade
    # transport security or reach an unexpected service.
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or port not in {None, 443}):
        return False
    host = (parsed.hostname or "").lower()
    domains = [str(x).lower().strip() for x in (source.get("search_domains") or []) if str(x).strip()]
    # Every allowed host must be registered explicitly. Listing an apex domain
    # must not implicitly trust arbitrary sibling subdomains.
    return host in domains

class FirstPartyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not source_host_allowed(newurl, self.source):
            raise ValueError("redirect left registered first-party domains")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_first_party(url, source, timeout=15, max_bytes=1200000, *, opener=None,
                      extra_headers=None):
    if not source_host_allowed(url, source):
        raise ValueError("URL is outside registered first-party domains")
    mobile = bool(source.get("mobile", True))
    ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
        if mobile else
        "Mozilla/5.0 (compatible; POIGAMELAB/1.0; +https://poigamelab.com/)"
    )
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
    }
    for key, value in (extra_headers or {}).items():
        if key in {"Referer", "X-Requested-With", "Accept"} and isinstance(value, str):
            headers[key] = value
    req = Request(url, headers=headers)
    opener = opener or build_opener(FirstPartyRedirectHandler(source))
    with opener.open(req, timeout=timeout) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not source_host_allowed(final_url, source):
            raise ValueError("redirect left registered first-party domains")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("response exceeds byte limit; incomplete evidence rejected")
        charset = None
        try:
            charset = response.headers.get_content_charset()
        except Exception:
            pass
    if not charset:
        # Some legacy Japanese first-party pages omit the HTTP charset while
        # declaring Shift_JIS in HTML. Sniff only the bounded response head.
        match = re.search(
            br"(?i)charset\s*=\s*['\"]?\s*([a-z0-9._-]+)",
            data[:16384],
        )
        if match:
            charset = match.group(1).decode("ascii", errors="ignore")
    try:
        decoded = data.decode(charset or "utf-8", errors="replace")
    except LookupError:
        decoded = data.decode("utf-8", errors="replace")
    return decoded, final_url


def source_participates_in_new_game_ranking(source):
    """Whether discovery health from this source can affect reward ranking."""
    return (
        source.get("scheduled_fetch_enabled", True) is True
        or (
            source.get("coverage_detail_review_enabled") is True
            and source.get("coverage_detail_review_mode") == "candidate_only"
        )
    )


def listing_session_required(url, source):
    bootstrap = str(source.get("listing_session_bootstrap_url") or "").strip()
    hints = [
        str(value).strip().lower()
        for value in (source.get("listing_session_url_hints") or [])
        if str(value).strip()
    ]
    if not bootstrap or not source_host_allowed(bootstrap, source) or not hints:
        return False
    try:
        parsed = urlparse(str(url or ""))
    except (TypeError, ValueError):
        return False
    combined = ((parsed.path or "") + "?" + (parsed.query or "")).lower()
    return any(hint in combined for hint in hints)


def summarize_fetch_error(error):
    """Keep diagnostic categories, never untrusted response/exception text.

    A status code describes this fetch, not the offer's availability. In
    particular, HTTPError subclasses URLError and must be checked first.
    """
    if isinstance(error, HTTPError):
        code = error.code
        return f"http_status_{code}" if type(code) is int and 100 <= code <= 599 else "http_error"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, URLError):
        return "timeout" if isinstance(error.reason, TimeoutError) else "network_error"
    if isinstance(error, ConnectionError):
        return "network_error"
    if isinstance(error, ValueError):
        return {
            "URL is outside registered first-party domains": "first_party_url_rejected",
            "redirect left registered first-party domains": "first_party_redirect_rejected",
            "response exceeds byte limit; incomplete evidence rejected": "response_too_large",
        }.get(str(error), "fetch_error")
    return "fetch_error"


def visible_text(raw):
    x = re.sub(r"(?is)<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)>", " ", raw or "")
    x = re.sub(r"(?s)<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", html.unescape(x)).strip()

def normalized_text(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()

def target_present(text, aliases):
    hay = normalized_text(text)
    return any(normalized_text(a) in hay for a in aliases if str(a).strip())

def detail_like(url, source):
    try:
        p = urlparse(url)
    except Exception:
        return False
    combined = ((p.path or "") + "?" + (p.query or "")).lower()
    hints = [str(x).lower() for x in (source.get("direct_detail_url_hints") or []) if str(x)]
    if any(h in combined for h in hints):
        return True
    query_keys = {x.split("=", 1)[0].lower() for x in (p.query or "").split("&") if "=" in x}
    if query_keys & DETAIL_QUERY_KEYS:
        return True
    return any(h in (p.path or "").lower() for h in (
        "pointentrance", "/ad_details/", "/campaigns/details/", "/ad/detail", "/item/detail/"
    ))

def target_listing_urls(source, aliases):
    """Return bounded first-party listing URLs for one target game.

    A source may provide a reviewed search template containing exactly one
    {query} placeholder. Only the primary alias is used so scheduled checks stay
    bounded and predictable. Generated URLs must still pass the first-party
    HTTPS allowlist before any fetch occurs.
    """
    configured = [
        str(x).strip() for x in (source.get("direct_listing_urls") or [])
        if str(x).strip()
    ]
    template = source.get("direct_search_url_template")
    if template is None:
        return configured
    if (not isinstance(template, str) or template.count("{query}") != 1
            or "{" in template.replace("{query}", "")
            or "}" in template.replace("{query}", "")):
        return configured
    primary = next((str(x).strip() for x in aliases if str(x).strip()), "")
    if not primary:
        return configured
    candidate = template.replace("{query}", quote_plus(primary, safe=""))
    if source_host_allowed(candidate, source):
        return [candidate] + configured
    return configured


def discover_detail_links(raw, base_url, source, aliases, limit=8):
    """Discover first-party detail links without leaking target context across cards."""
    found = []
    seen = set()
    try:
        anchors = EvidenceHTML(raw or "").root.find(tag="a")
    except (TypeError, ValueError, RecursionError):
        return found

    for anchor in anchors:
        href = html.unescape(anchor.attrs.get("href", "")).strip()
        absolute = urljoin(base_url, href)
        if not source_host_allowed(absolute, source) or not detail_like(absolute, source):
            continue

        anchor_label = evidence_text(anchor).strip()
        generic_labels = {
            "詳細", "詳細を見る", "もっと見る", "案件を見る", "ポイントを貯める",
            "参加する", "今すぐ参加", "こちら", "more", "detail"
        }
        anchor_label_is_descriptive = (
            bool(anchor_label)
            and anchor_label.casefold() not in generic_labels
            and 2 <= len(anchor_label) <= 240
        )

        # Descriptive detail links already bind title and URL to one offer.
        # Do not widen them to a shared mobile grid where a sibling target can
        # make unrelated links look like matches. Only generic/blank links may
        # borrow text from their nearest bounded card container.
        matched = target_present(anchor_label, aliases)
        if not anchor_label_is_descriptive:
            node = anchor.parent
            depth = 0
            while not matched and node is not None and node.parent is not None and depth < 4:
                marker = " ".join([
                    node.tag,
                    node.attrs.get("id", ""),
                    node.attrs.get("class", ""),
                ]).casefold()
                is_card_boundary = (
                    node.tag in {"article", "li", "tr"}
                    or any(token in marker for token in (
                        "card", "offer", "campaign", "service-item", "result-item"
                    ))
                )
                if is_card_boundary:
                    context = evidence_text(node)
                    if len(context) <= 1400 and target_present(context, aliases):
                        matched = True
                    break
                node = node.parent
                depth += 1

        if not matched:
            continue
        key = absolute.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        found.append(key)
        if len(found) >= limit:
            break
    return found

def discover_first_party_listing_candidates(raw, base_url, source, aliases, limit=8):
    """Return non-publishable first-party detail URL candidates from one listing.

    This only proves that a target-linked detail URL was present on an official
    listing page. Reward, platform, conditions, and publication eligibility
    remain unverified until the detail is independently reviewed.
    """
    detail_urls = discover_detail_links(raw, base_url, source, aliases, limit=limit)
    game_label = next((str(x).strip() for x in aliases if str(x).strip()), "")
    return [{
        "source": str(source.get("id") or ""),
        "sourceLabel": str(source.get("name") or source.get("id") or ""),
        "providerHint": "",
        "gameLabel": game_label,
        "platformHint": "",
        "rewardYenHint": "",
        "firstPartyCandidateUrl": url,
    } for url in detail_urls]

def normalized_game_title_key(value):
    """Conservative key for matching known game titles and aliases.

    This removes presentation punctuation/spacing and common platform suffixes
    but intentionally keeps substantive words and numbers.
    """
    text = html.unescape(str(value or "")).strip().casefold()
    text = re.sub(r"^(?:ios|android|and)[ _：:・\-]+", "", text, flags=re.I)
    text = re.sub(r"[（(](?:ios|android)[）)]$", "", text, flags=re.I)
    text = text.replace("＆", "&")
    text = re.sub(r"[\s・･·／/｜|：:‐‑‒–—―_\-]+", "", text)
    text = re.sub(r"[【】\[\]（）()「」『』〈〉《》]", "", text)
    return text[:220]


def known_game_title_keys(targets):
    keys = set()
    for target in targets or []:
        values = [target.get("game")] + list(target.get("aliases") or [])
        for value in values:
            key = normalized_game_title_key(value)
            if key:
                keys.add(key)
    return keys


def context_matches_known_game(context, targets):
    """Match known games using reviewed aliases plus conservative title keys."""
    text = str(context or "")
    aliases = []
    for target in targets or []:
        game = str(target.get("game") or "").strip()
        if game:
            aliases.append(game)
        aliases.extend(str(x).strip() for x in (target.get("aliases") or []) if str(x).strip())

    if target_present(text, aliases):
        return True

    context_key = normalized_game_title_key(text)
    if not context_key:
        return False
    for key in known_game_title_keys(targets):
        if len(key) >= 4 and key in context_key:
            return True
    return False


def new_game_title_cluster_key(value):
    """Conservative review-only title key for clustering new-game candidates.

    Only explicit OS decorations and whitespace are normalized. The key is not
    an identity and never authorizes game creation or publication.
    """
    text = html.unescape(str(value or "")).strip()
    text = re.sub(r"^(?:iOS|Android|And)[ _：:・-]+", "", text, flags=re.I)
    text = re.sub(r"[（(](?:iOS|Android)[）)]$", "", text, flags=re.I)
    text = re.sub(r"\s+", "", text).casefold()
    return text[:180]


def classify_new_game_candidate(item):
    """Assign a conservative review score for whether a new candidate is a game.

    This classifier never deletes candidates and never authorizes publication.
    It only prioritizes review by explicit positive/negative title signals.
    """
    title = str((item or {}).get("titleHint") or "").strip()
    normalized = normalized_text(title)
    score = 0
    reasons = []

    positive_markers = (
        "ゲーム", "rpg", "パズル", "シミュレーション", "ストラテジー",
        "放置", "育成", "バトル", "サバイバル", "冒険", "クエスト",
        "アプリゲーム", "game"
    )
    negative_markers = (
        "クレジットカード", "カード発行", "証券", "fx", "銀行口座",
        "口座開設", "保険", "ローン", "不動産", "電気",
        "宅配", "サブスク", "会員登録", "無料登録", "資料請求",
        "アンケート", "モニター", "ショッピング"
    )

    for marker in positive_markers:
        if normalized_text(marker) in normalized:
            score += 2
            reasons.append("positive:" + marker)
    for marker in negative_markers:
        if normalized_text(marker) in normalized:
            score -= 3
            reasons.append("negative:" + marker)
    if re.search(r"(?:都市|プロパン|lp)ガス|ガス(?:会社|料金|契約|切替|申込)", title, re.I):
        score -= 3
        reasons.append("negative:gas_service")

    if re.search(r"(?:lv|level|レベル)\s*\d+", title, re.I):
        score += 2
        reasons.append("positive:level")
    if re.search(r"(?:城|本部|司令部|ランク|ステージ)\s*\d+", title):
        score += 1
        reasons.append("positive:progress_condition")
    # App-offer titles often omit genre words entirely. Explicit in-game
    # progression/completion language is a stronger game signal than the name.
    progress_patterns = (
        r"ステージ\s*\d", r"\d+\s*ステージ", r"チャプター\s*\d",
        r"フロア\s*\d", r"ワールド\s*\d", r"(?:レベル|lv)\s*\d",
        r"(?:ステージ|チャプター|フロア|ワールド|boss|ボス).*?クリア",
        r"(?:勝利(?:数)?|プレイヤーレベル|勢力)\s*\d",
        r"(?:ステージ|チャプター|フロア|ワールド|アクティビティ|challenge)\s*\d",
        r"(?:ソリティア|solitaire|idle|fighter|kingdom|mafia|zombie|ゾンビ|勇者|魔王|商人|三國|三国|戦国|rpg|merge|マージ|waterpark|ハイローラー)",
    )
    if any(re.search(pattern, title, re.I) for pattern in progress_patterns):
        score += 2
        reasons.append("positive:explicit_game_progress")

    if re.search(r"(?:step\s*up|stepup|各成果地点到達|各ミッションクリア|ミッション全クリア)", title, re.I):
        score += 2
        reasons.append("positive:achievement_app")

    if score >= 2:
        bucket = "likely_game"
    elif score <= -2:
        bucket = "likely_non_game"
    else:
        bucket = "review"

    return {
        "classification": bucket,
        "scope": "achievement_app" if bucket == "likely_game" else "review",
        "classificationScore": score,
        "classificationReasons": reasons[:12],
        "classificationReviewOnly": True,
        "classificationAuthorized": False,
    }


def load_new_game_history(path):
    if not path.exists():
        return {"version": 1, "items": {}}
    try:
        value = load_json(path)
    except (OSError, ValueError, TypeError):
        return {"version": 1, "items": {}}
    if not isinstance(value, dict) or not isinstance(value.get("items"), dict):
        return {"version": 1, "items": {}}
    return value


def new_game_history_key(item):
    source = str((item or {}).get("source") or "").strip()
    identity = str((item or {}).get("offerIdentity") or "").strip()
    if source and identity:
        return source + "|" + identity
    url = str((item or {}).get("firstPartyCandidateUrl") or "").strip()
    return source + "|" + exact_url_key(url)


def build_new_game_history(current_items, previous, checked_at):
    """Track first/last seen without changing publication state."""
    previous_items = (previous or {}).get("items") if isinstance(previous, dict) else {}
    if not isinstance(previous_items, dict):
        previous_items = {}

    current_keys = set()
    out = {}
    for item in current_items or []:
        key = new_game_history_key(item)
        if not key:
            continue
        current_keys.add(key)
        prior = previous_items.get(key) if isinstance(previous_items.get(key), dict) else {}
        first_seen = str(prior.get("firstSeen") or checked_at)
        seen_count = int(prior.get("seenCount") or 0) + 1
        out[key] = {
            "source": str(item.get("source") or ""),
            "offerIdentity": str(item.get("offerIdentity") or ""),
            "titleHint": str(item.get("titleHint") or ""),
            "firstPartyCandidateUrl": str(item.get("firstPartyCandidateUrl") or ""),
            "firstSeen": first_seen,
            "lastSeen": checked_at,
            "seenCount": seen_count,
            "active": True,
            "isNewToday": first_seen == checked_at,
            "candidateOnly": True,
            "autoCreateAuthorized": False,
            "publicationAuthorized": False,
        }

    for key, prior in previous_items.items():
        if key in current_keys or not isinstance(prior, dict):
            continue
        stale = dict(prior)
        stale["active"] = False
        stale["isNewToday"] = False
        stale["lastMissingAt"] = checked_at
        stale["candidateOnly"] = True
        stale["autoCreateAuthorized"] = False
        stale["publicationAuthorized"] = False
        out[key] = stale

    return {
        "version": 1,
        "checkedAt": checked_at,
        "items": out,
    }


def build_new_game_review_priority(items, clusters):
    """Create review-only priorities from classification and source corroboration."""
    source_counts = {}
    candidate_counts = {}
    for cluster in clusters or []:
        key = str(cluster.get("clusterKey") or "")
        source_counts[key] = int(cluster.get("sourceCount") or 0)
        candidate_counts[key] = int(cluster.get("candidateCount") or 0)

    ranked = []
    for item in items or []:
        key = new_game_title_cluster_key(item.get("titleHint"))
        classification = str(item.get("classification") or "review")
        base = {"likely_game": 30, "review": 10, "likely_non_game": -20}.get(classification, 0)
        corroboration = min(source_counts.get(key, 0), 5) * 15
        duplicates = min(max(candidate_counts.get(key, 0) - 1, 0), 5) * 2
        total = base + corroboration + duplicates

        if total >= 55:
            band = "high"
        elif total >= 25:
            band = "medium"
        else:
            band = "low"

        ranked.append({
            "clusterKey": key,
            "titleHint": str(item.get("titleHint") or ""),
            "source": str(item.get("source") or ""),
            "classification": classification,
            "sourceCount": source_counts.get(key, 0),
            "reviewPriorityScore": total,
            "reviewPriority": band,
            "reviewOnly": True,
            "autoCreateAuthorized": False,
            "publicationAuthorized": False,
        })

    ranked.sort(
        key=lambda x: (-x["reviewPriorityScore"], -x["sourceCount"], x["titleHint"])
    )
    return ranked


def build_new_game_candidate_clusters(items):
    """Build review-only multi-source clusters without changing raw candidates."""
    buckets = {}
    for item in items or []:
        key = new_game_title_cluster_key(item.get("titleHint"))
        if not key:
            continue
        buckets.setdefault(key, []).append(item)

    clusters = []
    for key, members in buckets.items():
        sources = sorted({
            str(item.get("source") or "").strip()
            for item in members if str(item.get("source") or "").strip()
        })
        title_hints = []
        for item in members:
            title = str(item.get("titleHint") or "").strip()
            if title and title not in title_hints:
                title_hints.append(title)
        clusters.append({
            "clusterKey": key,
            "sourceCount": len(sources),
            "candidateCount": len(members),
            "sources": sources,
            "titleHints": title_hints[:12],
            "reviewOnly": True,
            "identityAuthorized": False,
            "autoCreateAuthorized": False,
            "publicationAuthorized": False,
        })

    return sorted(
        clusters,
        key=lambda item: (-item["sourceCount"], -item["candidateCount"], item["clusterKey"])
    )


def listing_anchor_in_scope(anchor, source):
    """Limit listing discovery to a reviewed first-party container when configured.

    Most sources expose only offer cards in their listing body. Powl also embeds
    sidebar rankings and trend links that point at /reward/<id>; treating those
    as part of the primary app listing inflates the discovery universe. A
    source-specific container class keeps the generic discovery code reusable
    while failing closed when the reviewed container is absent.
    """
    required_class = str(source.get("new_game_discovery_container_class") or "").strip()
    if not required_class:
        return True
    node = anchor.parent
    for _ in range(8):
        if node is None:
            break
        if required_class in node.attrs.get("class", "").split():
            return True
        node = node.parent
    return False


def listing_detail_identity_signature(raw, base_url, source, limit=5000):
    """Return a stable signature of first-party detail identities on one listing page."""
    identities = []
    seen = set()
    try:
        anchors = EvidenceHTML(raw or "").root.find(tag="a")
    except (TypeError, ValueError, RecursionError):
        return tuple()
    for anchor in anchors:
        href = html.unescape(anchor.attrs.get("href", "")).strip()
        absolute = urljoin(base_url, href).split("#", 1)[0]
        if not source_host_allowed(absolute, source) or not detail_like(absolute, source):
            continue
        if not listing_anchor_in_scope(anchor, source):
            continue
        identity = offer_identity_key(absolute, str(source.get("id") or ""))
        if not identity or identity in seen:
            continue
        seen.add(identity)
        identities.append(identity)
        if len(identities) >= max(1, min(int(limit or 5000), 5000)):
            break
    return tuple(sorted(identities))


def paginated_listing_url(source, page):
    template = source.get("new_game_discovery_page_url_template")
    if not isinstance(template, str) or template.count("{page}") != 1:
        return ""
    remainder = template.replace("{page}", "")
    if "{" in remainder or "}" in remainder:
        return ""
    candidate = template.replace("{page}", str(int(page)))
    return candidate if source_host_allowed(candidate, source) else ""


def discover_new_game_listing_candidates(raw, base_url, source, targets, limit=500):
    """Discover first-party detail links that do not map to a known game.

    This is discovery-only. A result never creates a game, publishes an offer,
    or trusts reward/condition text. Known games are suppressed by either a
    reviewed alias in bounded listing context or a known first-party offer
    identity.
    """
    known_identities = set()
    for target in targets or []:
        known_urls = (target.get("known_urls_by_source") or {}).get(str(source.get("id") or ""), [])
        for known_url in known_urls or []:
            identity = offer_identity_key(known_url, str(source.get("id") or ""))
            if identity:
                known_identities.add(identity)

    known_aliases = []
    for target in targets or []:
        game = str(target.get("game") or "").strip()
        if game:
            known_aliases.append(game)
        known_aliases.extend(
            str(x).strip() for x in (target.get("aliases") or []) if str(x).strip()
        )

    found = []
    seen = set()
    try:
        anchors = EvidenceHTML(raw or "").root.find(tag="a")
    except (TypeError, ValueError, RecursionError):
        return found

    generic_labels = {
        "詳細", "詳細を見る", "もっと見る", "案件を見る", "ポイントを貯める",
        "参加する", "今すぐ参加", "こちら", "more", "detail"
    }

    for anchor in anchors:
        href = html.unescape(anchor.attrs.get("href", "")).strip()
        absolute = urljoin(base_url, href).split("#", 1)[0]
        if not source_host_allowed(absolute, source) or not detail_like(absolute, source):
            continue
        if not listing_anchor_in_scope(anchor, source):
            continue

        identity = offer_identity_key(absolute, str(source.get("id") or ""))
        if not identity or identity in known_identities or identity in seen:
            continue

        raw_anchor_label = evidence_text(anchor).strip()
        anchor_label = raw_anchor_label
        if str(source.get("id") or "") == "kurashiru_reward":
            h3_values = [
                evidence_text(node).strip()
                for node in anchor.find(tag="h3")
                if evidence_text(node).strip()
            ]
            if len(h3_values) == 1:
                anchor_label = h3_values[0]
        anchor_label_is_descriptive = (
            bool(anchor_label)
            and anchor_label.casefold() not in generic_labels
            and 2 <= len(anchor_label) <= 240
        )

        context = anchor_label
        node = anchor.parent
        depth = 0
        while node is not None and node.parent is not None and depth < 4:
            marker = " ".join([
                node.tag,
                node.attrs.get("id", ""),
                node.attrs.get("class", ""),
            ]).casefold()
            bounded = (
                node.tag in {"article", "li", "tr"}
                or any(token in marker for token in (
                    "card", "offer", "campaign", "service-item", "result-item", "item"
                ))
            )
            candidate_context = evidence_text(node)
            if candidate_context and len(candidate_context) <= 1400:
                context = candidate_context
            if bounded:
                break
            node = node.parent
            depth += 1

        # A descriptive first-party detail link is the narrowest offer identity.
        # Do not let a loose mobile grid ancestor containing a different known
        # game suppress every sibling offer. Generic links such as "詳細" still
        # require bounded surrounding context for known-game suppression.
        known_game_context = anchor_label if anchor_label_is_descriptive else context
        if context_matches_known_game(known_game_context, targets):
            continue

        title_hint = anchor_label
        if (not title_hint or title_hint.casefold() in generic_labels
                or len(title_hint) < 2 or len(title_hint) > 160):
            title_hint = context[:160].strip()
        if not title_hint:
            title_hint = "(title review required)"

        seen.add(identity)
        found.append({
            "source": str(source.get("id") or ""),
            "sourceLabel": str(source.get("name") or source.get("id") or ""),
            "titleHint": title_hint,
            "listingRewardText": (
                raw_anchor_label[:600]
                if str(source.get("id") or "") == "kurashiru_reward"
                else ""
            ),
            "firstPartyCandidateUrl": absolute,
            "offerIdentity": identity,
            "discoveryEvidence": "first_party_listing",
            "discoveryScope": str(source.get("new_game_discovery_scope")
                                  or source.get("coverage_scope") or "unspecified"),
            "fullCatalogObserved": source.get("full_catalog_discovery_enabled") is True,
            "candidateOnly": True,
            "firstPartyVerificationRequired": True,
            "autoCreateAuthorized": False,
            "publicationAuthorized": False,
        })
        if len(found) >= max(1, min(int(limit or 500), 2000)):
            break
    return found


def discover_offerwall_presence(raw, base_url, aliases, known_domains, limit=6):
    """Detect same-card offerwall links without following or storing them.

    Only normalized provider hostnames are returned. A target alias must appear
    in the anchor label or a bounded ancestor container; page-wide proximity is
    intentionally insufficient.
    """
    allowed = {str(x).lower().strip() for x in (known_domains or []) if str(x).strip()}
    found = []
    seen = set()
    try:
        anchors = EvidenceHTML(raw or "").root.find(tag="a")
    except (TypeError, ValueError, RecursionError):
        return found

    for anchor in anchors:
        href = html.unescape(anchor.attrs.get("href", "")).strip()
        try:
            p = urlparse(urljoin(base_url, href))
            port = p.port
        except (TypeError, ValueError):
            continue
        host = (p.hostname or "").lower()
        if (p.scheme != "https" or p.username is not None or p.password is not None
                or port not in {None, 443} or host not in allowed):
            continue

        matched = target_present(evidence_text(anchor), aliases)
        node = anchor.parent
        depth = 0
        while not matched and node is not None and node.parent is not None and depth < 4:
            context = evidence_text(node)
            # A large container is effectively page-wide and is not acceptable
            # evidence that the target belongs to this specific offerwall link.
            if len(context) > 1400:
                break
            if target_present(context, aliases):
                matched = True
                break

            marker = " ".join([
                node.tag,
                node.attrs.get("id", ""),
                node.attrs.get("class", ""),
            ]).casefold()
            is_card_boundary = (
                node.tag in {"article", "li", "tr"}
                or any(token in marker for token in ("card", "offer", "campaign", "service-item"))
            )
            if is_card_boundary:
                break
            node = node.parent
            depth += 1
        if not matched:
            continue

        if host in seen:
            continue
        seen.add(host)
        found.append(host)
        if len(found) >= limit:
            break
    return found

def coverage_query_url(discovery_source, aliases):
    """Build one bounded external comparison query URL for candidate discovery only."""
    template = discovery_source.get("query_url_template")
    if (not isinstance(template, str) or template.count("{query}") != 1
            or "{" in template.replace("{query}", "")
            or "}" in template.replace("{query}", "")):
        return ""
    primary = next((str(x).strip() for x in aliases if str(x).strip()), "")
    if not primary:
        return ""
    candidate = template.replace("{query}", quote_plus(primary, safe=""))
    return candidate if source_host_allowed(candidate, discovery_source) else ""


def _coverage_yen_hint(raw):
    value = str(raw or "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def discover_dokotoku_candidates(raw, aliases, discovery_source, limit=24):
    """Extract review-only hints from Dokotoku's reward/source/os/title rows."""
    text = visible_text(raw)
    if not target_present(text, aliases):
        return []

    mappings = discovery_source.get("candidate_source_aliases") or []
    candidates = []
    occurrence = 0
    for mapping in mappings:
        source_id = str(mapping.get("source") or "").strip()
        provider_hint = str(mapping.get("providerHint") or "").strip()
        labels = sorted(
            {str(x).strip() for x in (mapping.get("labels") or []) if str(x).strip()},
            key=len,
            reverse=True,
        )
        if not source_id or not labels:
            continue

        occupied = []
        for label in labels:
            start = 0
            while True:
                pos = text.find(label, start)
                if pos < 0:
                    break
                start = pos + len(label)
                if any(a <= pos < b for a, b in occupied):
                    continue
                occupied.append((pos, pos + len(label)))

                left = text[max(0, pos - 90):pos]
                reward_matches = list(re.finditer(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*円", left))
                if not reward_matches:
                    continue
                reward_yen = _coverage_yen_hint(reward_matches[-1].group(1))
                if reward_yen is None:
                    continue

                right = text[pos + len(label):pos + len(label) + 180]
                alias_hits = []
                for alias in aliases:
                    alias_value = str(alias or "").strip()
                    if not alias_value:
                        continue
                    alias_pos = right.find(alias_value)
                    if alias_pos >= 0:
                        alias_hits.append((alias_pos, alias_value))
                if not alias_hits:
                    continue
                alias_pos, alias_value = min(alias_hits, key=lambda item: item[0])
                if alias_pos > 90:
                    continue

                between = right[:alias_pos]
                platform = ""
                if re.search(r"(?:^|\s)a(?:\s|$)", between, flags=re.I):
                    platform = "Android"
                elif re.search(r"(?:^|\s)i(?:\s|$)", between, flags=re.I):
                    platform = "iOS"
                elif re.search(r"(?:^|\s)s(?:\s|$)", between, flags=re.I):
                    platform = ""

                occurrence += 1
                candidates.append({
                    "source": source_id,
                    "sourceLabel": label,
                    "providerHint": provider_hint,
                    "gameLabel": alias_value,
                    "platformHint": platform,
                    "rewardYenHint": reward_yen,
                    "occurrence": occurrence,
                })
                if len(candidates) >= max(1, min(int(limit or 24), 60)):
                    return candidates
    return candidates


def discover_coverage_candidates(raw, aliases, discovery_source, limit=24):
    """Extract review-only source/platform/reward hints from a comparison page.

    Third-party comparison data is never publication evidence. The parser uses
    short windows around configured source labels so unrelated page-wide values
    cannot silently become candidates.
    """
    if discovery_source.get("parser") == "dokotoku-row-v1":
        return discover_dokotoku_candidates(raw, aliases, discovery_source, limit=limit)

    text = visible_text(raw)
    if not target_present(text, aliases):
        return []

    mappings = discovery_source.get("candidate_source_aliases") or []
    candidates = []
    occurrence = 0
    for mapping in mappings:
        source_id = str(mapping.get("source") or "").strip()
        provider_hint = str(mapping.get("providerHint") or "").strip()
        labels = [str(x).strip() for x in (mapping.get("labels") or []) if str(x).strip()]
        if not source_id or not labels:
            continue
        # Longest labels first prevents "ハピタス" from shadowing
        # "ハピタス（AppDriver）" at the same location.
        labels = sorted(set(labels), key=len, reverse=True)
        occupied = []
        for label in labels:
            start = 0
            while True:
                pos = text.find(label, start)
                if pos < 0:
                    break
                start = pos + len(label)
                if any(a <= pos < b for a, b in occupied):
                    continue
                occupied.append((pos, pos + len(label)))

                left = text[max(0, pos - 260):pos]
                # The candidate title and reward must be close to the source
                # label. A page-wide target mention is intentionally insufficient.
                alias_positions = []
                for alias in aliases:
                    alias_norm = str(alias or "").strip()
                    if not alias_norm:
                        continue
                    p = left.rfind(alias_norm)
                    if p >= 0:
                        alias_positions.append((p, alias_norm))
                if not alias_positions:
                    continue
                alias_pos, alias_value = max(alias_positions, key=lambda item: item[0])
                segment = left[alias_pos:] + " " + label
                if len(segment) > 300:
                    continue
                reward_matches = list(re.finditer(r"([0-9][0-9,]*)\s*円", segment))
                if not reward_matches:
                    continue
                reward_yen = _to_int(reward_matches[-1].group(1))
                if reward_yen is None:
                    continue

                platform = platform_hint(segment)
                occurrence += 1
                candidates.append({
                    "source": source_id,
                    "sourceLabel": label,
                    "providerHint": provider_hint,
                    "gameLabel": alias_value,
                    "platformHint": platform,
                    "rewardYenHint": reward_yen,
                    "occurrence": occurrence,
                })
                if len(candidates) >= max(1, min(int(limit or 24), 60)):
                    return candidates
    return candidates


def coverage_candidate_is_covered(candidate, rows, game):
    """Return True only when a current public row already covers the hint.

    Reward/platform hints from comparison pages are not trusted as facts; they
    are used only to decide whether first-party verification work is missing.
    First-party listing candidates are matched by exact offer identity so two
    distinct detail URLs cannot collapse into one generic source-level match.
    """
    source_id = str(candidate.get("source") or "")
    reward = str(candidate.get("rewardYenHint") or "")
    platform = str(candidate.get("platformHint") or "")
    candidate_url = str(candidate.get("firstPartyCandidateUrl") or "")
    candidate_identity = offer_identity_key(candidate_url, source_id) if candidate_url else ""
    for row in rows:
        if str(row.get("game") or "") != game or str(row.get("site") or "") != source_id:
            continue
        if candidate_identity:
            row_identity = offer_identity_key(str(row.get("url") or ""), source_id)
            if not row_identity or row_identity != candidate_identity:
                continue
        if reward and str(row.get("reward") or "") != reward:
            continue
        stored_platform = str(row.get("platform") or "")
        if platform and platform != "iOS|Android" and stored_platform != platform:
            continue
        return True
    return False


def coverage_candidate_key(game, candidate, discovery_source_id=""):
    """Stable key for deduplicating review-only coverage gaps."""
    return (
        str(game or ""),
        str(candidate.get("source") or ""),
        str(candidate.get("providerHint") or ""),
        str(candidate.get("platformHint") or ""),
        str(candidate.get("rewardYenHint") or ""),
        str(candidate.get("firstPartyCandidateUrl") or ""),
        str(discovery_source_id or ""),
    )


def coverage_candidate_queue_item(game, candidate, discovery_source_id, discovery_url, checked_at, sources):
    """Build one non-publishable coverage-gap queue item.

    Third-party comparison data or a first-party listing presence is discovery
    evidence only. The explicit safety flags below are intentionally redundant
    so downstream tooling cannot treat this file as publication evidence.
    """
    candidate_source = str(candidate.get("source") or "")
    first_party_candidate_url = str(candidate.get("firstPartyCandidateUrl") or "")
    return {
        "game": str(game or ""),
        "source": candidate_source,
        "sourceLabel": candidate.get("sourceLabel"),
        "providerHint": candidate.get("providerHint"),
        "platformHint": candidate.get("platformHint"),
        "rewardYenHint": candidate.get("rewardYenHint"),
        "firstPartyCandidateUrl": first_party_candidate_url,
        "discoverySource": str(discovery_source_id or ""),
        "discoveryUrl": str(discovery_url or ""),
        "registeredSource": candidate_source in sources,
        "verificationState": (
            "first_party_detail_required" if first_party_candidate_url else "first_party_required"
        ),
        "firstPartyVerificationRequired": True,
        "publicationAuthorized": False,
        "candidateOnly": True,
        "checkedAt": checked_at,
    }


def _to_int(raw):
    digits = re.sub(r"[^\d]", "", str(raw or ""))
    if not digits:
        return None
    value = int(digits)
    if value <= 0 or value >= 1000000:
        return None
    return value

def reward_candidates(text):
    t = str(text or "")
    strong = []
    weak = []
    generic = []
    strong_patterns = [
        r"(?:累計|合計|総額|合計獲得)\s*[：:]?\s*(?:約)?\s*([0-9][0-9,]*)\s*(?:pt|ポイント|P|円)",
    ]
    weak_patterns = [
        r"(?:最大獲得|最大|最高還元)\s*[：:]?\s*(?:約)?\s*([0-9][0-9,]*)\s*(?:pt|ポイント|P|円)",
        r"(?:獲得ポイント|獲得pt|獲得P)\s*[：:]?\s*([0-9][0-9,]*)\s*(?:pt|ポイント|P|円)?",
    ]
    for pat in strong_patterns:
        for m in re.finditer(pat, t, re.I):
            v = _to_int(m.group(1))
            if v is not None:
                strong.append(v)
    for pat in weak_patterns:
        for m in re.finditer(pat, t, re.I):
            v = _to_int(m.group(1))
            if v is not None:
                weak.append(v)
    for m in re.finditer(r"(?<![\d,])([0-9][0-9,]*)\s*(?:pt|ポイント|P|円)(?![ぁ-んァ-ヶ一-龠])", t, re.I):
        v = _to_int(m.group(1))
        if v is not None:
            generic.append(v)
    return sorted(set(strong)), sorted(set(weak)), sorted(set(generic))

def choose_existing_reward(text, old_reward):
    strong, weak, generic = reward_candidates(text)
    if len(strong) == 1:
        candidate = strong[0]
        method = "explicit_total_marker"
    elif len(strong) > 1:
        return None, "ambiguous_total_markers", strong, weak, generic
    elif len(weak) == 1:
        candidate = weak[0]
        method = "single_reward_marker"
    else:
        return None, "no_unambiguous_reward_marker", strong, weak, generic

    if old_reward > 0:
        ratio = candidate / old_reward
        if ratio < 0.40 or ratio > 2.50:
            return None, "reward_change_outside_safety_band", strong, weak, generic
    return candidate, method, strong, weak, generic

def platform_hint(text):
    low = str(text or "").casefold()
    ios = "ios" in low or "iphone" in low
    android = "android" in low
    if ios and not android:
        return "iOS"
    if android and not ios:
        return "Android"
    if ios and android:
        return "iOS|Android"
    return ""

def read_published():
    if not PUBLISHED.exists():
        return []
    with PUBLISHED.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def write_published(rows):
    tmp = PUBLISHED.with_suffix(PUBLISHED.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(PUBLISHED)

def exact_url_key(url):
    try:
        p = urlparse(str(url or ""))
    except Exception:
        return ""
    if p.scheme not in {"http", "https"}:
        return ""
    return p._replace(fragment="").geturl()

def offer_identity_key(url, source_id):
    """Stable first-party offer identity across harmless URL variants.

    Point sites commonly move the same offer between www/ssl hosts or add
    navigation query parameters. Prefer the site's stable numeric offer ID
    when present, then fall back to well-known numeric detail paths.
    """
    exact = exact_url_key(url)
    if not exact:
        return ""
    try:
        p = urlparse(exact)
        query = parse_qs(p.query, keep_blank_values=False)
    except Exception:
        return f"{source_id}:url:{exact}"

    for key in ("point_id", "site_id", "s_id", "itemid", "campaign_id", "campaignid", "cd_client", "id"):
        values = query.get(key) or []
        if values:
            value = str(values[0]).strip()
            if value:
                return f"{source_id}:{key}:{value}"

    path = p.path or ""
    for pattern in (
        r"/ad_details/(\d+)",
        r"/campaigns/details/(\d+)",
        r"/item/detail/itemid/(\d+)",
        r"/shopping/(\d+)",
        r"/service/item/(\d+)",
        r"/ad/(\d+)/show/",
        r"/reward/(\d+)",
        r"/ads?/(\d+)",
        r"/item/(\d+)",
        r"/detail/id/(\d+)",
    ):
        m = re.search(pattern, path, re.I)
        if m:
            return f"{source_id}:pathid:{m.group(1)}"

    return f"{source_id}:url:{exact}"

class EvidenceNode:
    def __init__(self, tag="", attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def text(self):
        if self.tag in {"script", "style", "noscript", "svg"}:
            return ""
        return " ".join(c.text() if isinstance(c, EvidenceNode) else c for c in self.children)

    def find(self, *, tag=None, ident=None, cls=None):
        found = []
        for child in self.children:
            if not isinstance(child, EvidenceNode):
                continue
            if ((tag is None or child.tag == tag)
                    and (ident is None or child.attrs.get("id") == ident)
                    and (cls is None or cls in child.attrs.get("class", "").split())):
                found.append(child)
            found.extend(child.find(tag=tag, ident=ident, cls=cls))
        return found


class EvidenceHTML(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.root = self.current = EvidenceNode()
        self.feed(raw)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = EvidenceNode(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def evidence_text(node):
    return re.sub(r"\s+", " ", node.text()).strip()


def one(nodes):
    if len(nodes) != 1:
        raise ValueError("missing_or_ambiguous_offer_structure")
    return nodes[0]


def warau_offer_id(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname not in {"www.warau.jp", "ssl.warau.jp"}
            or p.path != "/contents/point/pointEntrance.php"):
        raise ValueError("unexpected_offer_url")
    values = parse_qs(p.query, keep_blank_values=True).get("point_id", [])
    if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
        raise ValueError("ambiguous_offer_identity")
    return values[0]


def exact_points(node):
    value = evidence_text(node)
    if not re.fullmatch(r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", value):
        raise ValueError("invalid_points")
    number = int(value.replace(",", ""))
    if not 0 < number < 1_000_000:
        raise ValueError("invalid_points")
    return number


def inspect_warau_offer(raw, requested_url, final_url, aliases):
    """Extract review evidence from observed Warau desktop StepUp markup only.

    No point-to-yen conversion or publication is authorized by this parser.
    Full terms must be reviewed; a matching summary is not a verified snapshot.
    """
    try:
        offer_id = warau_offer_id(requested_url)
        if warau_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")
        doc = EvidenceHTML(raw).root
        canonical = one([n for n in doc.find(tag="link")
                         if "canonical" in n.attrs.get("rel", "").split()])
        if warau_offer_id(urljoin(final_url, canonical.attrs.get("href", ""))) != offer_id:
            raise ValueError("canonical_offer_mismatch")
        title = evidence_text(one(doc.find(tag="title")))
        if doc.find(cls="pointEntranceNone-Main") or "掲載終了のご案内" in title:
            return {"state": "unavailable", "reason": "source_offer_unavailable",
                    "offerId": offer_id}
        root = one(doc.find(ident="pointEntrancePointDetail"))
        header = one(root.find(ident="innerEntranceBox"))
        name = evidence_text(one(header.find(cls="pointEntrance-Head_Title")))
        if not target_present(name, aliases):
            raise ValueError("offer_title_mismatch")
        platform = evidence_text(one(header.find(cls="pointEntrance-BannerBox_SpLabelText")))
        if platform not in {"iOS", "Android"}:
            raise ValueError("ambiguous_offer_platform")
        table = one(header.find(cls="sw-SurInfo_PtList"))
        steps = []
        for row in table.find(tag="tr"):
            cells = row.find(tag="td")
            if not cells:
                continue
            if len(cells) != 2:
                raise ValueError("incomplete_step_row")
            condition = evidence_text(one(row.find(cls="sw-SurInfo_PtListAcquirement")))
            if len(condition) < 4:
                raise ValueError("missing_step_condition")
            if evidence_text(one(row.find(cls="sw-PtUnit"))) != "pt":
                raise ValueError("unexpected_reward_unit")
            steps.append({"condition": condition,
                          "rewardPoints": exact_points(one(row.find(cls="sw-Pt")))})
        if not steps or len({s["condition"] for s in steps}) != len(steps):
            raise ValueError("missing_or_duplicate_steps")
        cumulative = one(header.find(cls="sw-SurInfo_PtListCumulative"))
        if evidence_text(one(cumulative.find(cls="sw-PtUnit"))) != "pt":
            raise ValueError("unexpected_reward_unit")
        total = exact_points(one(cumulative.find(cls="sw-Pt")))
        summary = one(header.find(ident="detailPointContainer"))
        if evidence_text(one(summary.find(cls="entrance-ptItem_PtInfo-unit"))) != "pt":
            raise ValueError("unexpected_reward_unit")
        if (sum(s["rewardPoints"] for s in steps) != total
                or exact_points(one(summary.find(cls="entrance-ptItem_PtInfo-point"))) != total):
            raise ValueError("step_total_mismatch")
        terms = evidence_text(one(root.find(ident="js_cautionDiv")))
        if not all(marker in terms for marker in ("獲得条件", "獲得対象外", "注意事項")):
            raise ValueError("incomplete_offer_terms")
        payload = {"offerId": offer_id, "name": name, "platform": platform,
                   "rewardPoints": total, "rewardUnit": "pt", "steps": steps,
                   "termsText": terms}
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()
        return {"state": "parsed", "parserVersion": "warau-stepup-v1",
                **payload, "evidenceFingerprint": fingerprint}
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def chobirich_offer_id(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname not in {"www.chobirich.com", "chobirich.com"}
            or p.username is not None or p.password is not None or p.port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/ad_details/([0-9]+)/?", p.path)
    if not match:
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def evidence_lines(node):
    """Keep explicit line breaks for numbered conditions; ignore script content."""
    if node.tag == "br":
        return "\n"
    if node.tag in {"script", "style", "noscript", "svg"}:
        return ""
    return "".join(evidence_lines(c) if isinstance(c, EvidenceNode) else c for c in node.children)


def inspect_chobirich_offer(raw, requested_url, final_url, aliases):
    """Review-only parser for the observed numbered StepUp DOM variant.

    This does not authorize browser-backed collection or publication. Raw HTTP
    lacking the rendered yen summary or full terms must remain held for review.
    """
    try:
        offer_id = chobirich_offer_id(requested_url)
        if chobirich_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")
        doc = EvidenceHTML(raw).root
        canonical = one([n for n in doc.find(tag="link")
                         if "canonical" in n.attrs.get("rel", "").split()])
        if chobirich_offer_id(urljoin(final_url, canonical.attrs.get("href", ""))) != offer_id:
            raise ValueError("canonical_offer_mismatch")
        root = one(doc.find(tag="main"))
        name = evidence_text(one(root.find(tag="h1")))
        if not target_present(name, aliases):
            raise ValueError("offer_title_mismatch")
        yen_node = one(root.find(ident="item_yen"))
        yen_match = re.fullmatch(r"\(最大([0-9,]+)円相当\)", evidence_text(yen_node).replace(" ", ""))
        if not yen_match:
            raise ValueError("missing_explicit_yen_total")
        total_yen = exact_points(EvidenceHTML(yen_match.group(1)).root)
        point_node = one([n for n in yen_node.parent.children
                          if isinstance(n, EvidenceNode) and n.tag == "p" and n is not yen_node])
        point_match = re.fullmatch(r"最大([0-9,]+)ポイント", evidence_text(point_node))
        if not point_match:
            raise ValueError("missing_explicit_point_total")
        total_points = exact_points(EvidenceHTML(point_match.group(1)).root)
        if total_points != total_yen:
            raise ValueError("source_reward_conversion_mismatch")
        os_labels = []
        for button in root.find(tag="button"):
            label = evidence_text(button)
            if label.startswith("QRコードを表示してスマホで利用する"):
                match = re.fullmatch(r"QRコードを表示してスマホで利用する\((Android|iOS)用\)", label)
                if not match:
                    raise ValueError("ambiguous_offer_platform")
                os_labels.append(match.group(1))
        if len(set(os_labels)) != 1:
            raise ValueError("ambiguous_offer_platform")
        requirement = one(root.find(cls="ad-requirement"))
        heading = evidence_text(one(requirement.find(tag="h2")))
        if not heading.startswith("獲得方法：") or "各ステップクリア" not in heading:
            raise ValueError("unsupported_achievement_method")
        paragraph = one(requirement.find(tag="p"))
        lines = [re.sub(r"\s+", " ", line).strip() for line in evidence_lines(paragraph).splitlines()]
        lines = [line for line in lines if line]
        steps, rest = [], []
        for line in lines:
            numbered = re.match(r"[0-9]+\.", line)
            if numbered:
                match = re.fullmatch(r"([1-9][0-9]*)\.\s*(.+)で([0-9,]+)pt", line)
                if not match or rest or int(match.group(1)) != len(steps) + 1:
                    raise ValueError("incomplete_numbered_steps")
                condition = match.group(2)
                if len(condition) < 4:
                    raise ValueError("missing_step_condition")
                steps.append({"condition": condition,
                              "rewardPoints": exact_points(EvidenceHTML(match.group(3)).root)})
            else:
                rest.append(line)
        if len(steps) < 2 or len({s["condition"] for s in steps}) != len(steps):
            raise ValueError("missing_or_duplicate_steps")
        if sum(s["rewardPoints"] for s in steps) != total_points:
            raise ValueError("step_total_mismatch")
        terms = "\n".join(lines)
        if not all(marker in "\n".join(rest) for marker in (
                "成果受付期限", "成果調査受付期限", "条件達成に関する注意事項", "却下条件")):
            raise ValueError("incomplete_offer_terms")
        payload = {"offerId": offer_id, "name": name, "platform": os_labels[0],
                   "rewardPoints": total_points, "rewardUnit": "pt", "observedRewardYen": total_yen,
                   "steps": steps, "termsText": terms}
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()
        return {"state": "parsed", "parserVersion": "chobirich-numbered-stepup-v1",
                **payload, "evidenceFingerprint": fingerprint}
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def coincome_offer_id(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname != "cimcome.jp"
            or p.username is not None or p.password is not None or p.port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/campaigns/details/([0-9]+)/?", p.path)
    if not match or p.query:
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_coincome_offer(raw, requested_url, final_url, aliases):
    """Parse the current first-party COINCOME campaign detail structure.

    The live page binds offer identity, title, platform and current reward in
    dedicated sale nodes. A nested span may contain a previous/base reward
    during boosted campaigns, so only the direct text of the reward paragraph
    is accepted as the current displayed amount. StepUp pages are additionally
    checked by summing the per-step yen amounts.
    """
    try:
        offer_id = coincome_offer_id(requested_url)
        if coincome_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical_url = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if coincome_offer_id(canonical_url) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        text = visible_text(raw)
        title_nodes = doc.find(cls="sale__title")
        if not title_nodes:
            if any(marker in text for marker in (
                "ページが見つかりません", "404 Not Found", "Not Found"
            )):
                return {
                    "state": "unavailable",
                    "reason": "source_offer_unavailable",
                    "offerId": offer_id,
                }
            raise ValueError("missing_or_ambiguous_offer_structure")
        title = evidence_text(one(title_nodes))
        title_key = normalized_text(title)
        alias_keys = [
            normalized_text(value)
            for value in aliases
            if str(value or "").strip()
        ]
        if not any(
            key and len(key) >= 4 and (key in title_key or title_key in key)
            for key in alias_keys
        ):
            raise ValueError("offer_title_mismatch")

        platform_match = re.match(r"^(iOS|Android)[ _：:・-]+", title, flags=re.I)
        if not platform_match:
            raise ValueError("ambiguous_offer_platform")
        platform = "iOS" if platform_match.group(1).casefold() == "ios" else "Android"
        name = re.sub(r"^(?:iOS|Android)[ _：:・-]+", "", title, flags=re.I).strip()

        reward_region = one(doc.find(cls="sale__up"))
        reward_paragraph = one(reward_region.find(tag="p"))
        direct_reward_text = re.sub(
            r"\s+",
            " ",
            "".join(
                child for child in reward_paragraph.children
                if isinstance(child, str)
            ),
        ).strip()
        reward_matches = re.findall(
            r"(?<![0-9,])([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)\s*円",
            direct_reward_text,
        )
        if len(reward_matches) != 1:
            raise ValueError("ambiguous_displayed_reward")
        reward_yen = int(reward_matches[0].replace(",", ""))
        if not 0 < reward_yen < 1_000_000:
            raise ValueError("invalid_displayed_reward")

        description_nodes = doc.find(cls="description")
        description = evidence_text(one(description_nodes)) if description_nodes else ""
        step_reward_yen = [
            int(value.replace(",", ""))
            for value in re.findall(
                r"STEP\s*[0-9]+\..*?【([0-9][0-9,]*)\s*円】",
                description,
                flags=re.I,
            )
        ]
        step_total_yen = sum(step_reward_yen) if step_reward_yen else None
        if step_reward_yen and step_total_yen != reward_yen:
            raise ValueError("step_total_mismatch")

        title_pos = text.find(title)
        condition_start = text.find("適用端末", max(0, title_pos))
        if condition_start < 0:
            raise ValueError("incomplete_offer_terms")
        condition_end_candidates = [
            value for value in (
                text.find("リンクをコピーする", condition_start),
                text.find("© COINCOME", condition_start),
            ) if value >= 0
        ]
        if not condition_end_candidates:
            raise ValueError("incomplete_offer_terms")
        terms = text[condition_start:min(condition_end_candidates)].strip()

        required = ("適用端末", "キャッシュバック条件", "承認条件", "否認条件")
        marker_positions = [terms.find(marker) for marker in required]
        if (
            any(position < 0 for position in marker_positions)
            or marker_positions != sorted(marker_positions)
        ):
            raise ValueError("incomplete_offer_terms")
        if not re.search(r"(?:[0-9]+\s*(?:日|時間)以内|翌日以内|当日中)", terms):
            raise ValueError("achievement_deadline_not_explicit")

        payload = {
            "offerId": offer_id,
            "name": name,
            "offerTitle": title,
            "platform": platform,
            "displayedRewardYen": reward_yen,
            "rewardUnit": "JPY-equivalent",
            "stepRewardYen": step_reward_yen,
            "stepTotalYen": step_total_yen,
            "headerText": f"{title} {direct_reward_text}".strip(),
            "termsText": terms,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "coincome-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}

def hapitas_offer_id(url):
    try:
        p = urlparse(str(url or ""))
        port = p.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (p.scheme != "https" or p.hostname not in {"hapitas.jp", "www.hapitas.jp"}
            or p.username is not None or p.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(
        r"/item/detail/itemid/([0-9]+)(?:/apn(?:/[A-Za-z0-9_-]+)?)?/?",
        p.path or "",
    )
    if not match:
        raise ValueError("unexpected_offer_url")
    if parse_qs(p.query, keep_blank_values=True):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_hapitas_offer(
        raw, requested_url, final_url, aliases,
        reviewed_platform="", publication_authorized=False):
    """Extract bounded current Hapitas evidence from one first-party item page.

    Hapitas repeats the item title in breadcrumbs/share chrome, so title
    uniqueness is not a safe current-page invariant. The reviewed v2 contract
    scopes the current reward to the first item-title through the first
    ポイント対象条件 header window, requires Hapitas' 1pt=1JPY marker,
    and cross-checks StepUp totals when steps are present. Platform is accepted
    only when explicit in the item title or supplied by the version-controlled
    reviewed offer-id registry.
    """
    try:
        offer_id = hapitas_offer_id(requested_url)
        if hapitas_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if hapitas_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        title = evidence_text(one(doc.find(tag="h1")))
        if not target_present(title, aliases):
            raise ValueError("offer_title_mismatch")

        bodies = doc.find(tag="body")
        if len(bodies) != 1:
            raise ValueError("missing_or_ambiguous_offer_body")
        text = evidence_text(bodies[0])

        # The first body occurrence is the item header/breadcrumb region on the
        # reviewed desktop page. Repeated title mentions later in share/review
        # chrome are intentionally ignored.
        title_pos = text.find(title)
        if title_pos < 0:
            raise ValueError("missing_offer_header")
        target_pos = text.find("ポイント対象条件", title_pos)
        if target_pos <= title_pos or target_pos - title_pos > 4000:
            raise ValueError("missing_offer_header_boundary")
        header = text[title_pos:target_pos]

        if "この広告は終了しています" in header:
            unavailable_payload = {
                "offerId": offer_id,
                "name": title,
                "unavailableMarker": "この広告は終了しています",
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    unavailable_payload, ensure_ascii=False, sort_keys=True
                ).encode("utf-8")
            ).hexdigest()
            return {
                "state": "unavailable",
                "reason": "source_offer_unavailable",
                "parserVersion": "hapitas-detail-review-v2",
                **unavailable_payload,
                "evidenceFingerprint": fingerprint,
            }

        if not re.search(r"1\s*ポイント\s*[=＝]\s*1\s*円", text):
            raise ValueError("unit_conversion_review_required")

        # Bind reward to Hapitas' current-item CTA sentence. Related-OS cards
        # may contain other pt values in the same header and must never win by
        # position or magnitude.
        reward_matches = re.findall(
            r"(?:【ポイント獲得条件】の達成で|"
            r"インストール後、条件達成で|"
            r"アプリ複数条件達成で|"
            r"条件達成で)\s*"
            r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt\b",
            header,
            re.I,
        )
        reward_values = {int(value.replace(",", "")) for value in reward_matches}
        if len(reward_values) != 1:
            raise ValueError("missing_or_ambiguous_displayed_reward")
        displayed_reward = next(iter(reward_values))
        if not (0 < displayed_reward <= 5_000_000):
            raise ValueError("invalid_displayed_reward")

        terms_start = target_pos
        # "レビュー" can be ordinary ad-description text immediately after
        # ポイント対象条件 (for example Tokyo Debunker), so it is not a safe
        # boundary. The reviewed footer marker is stable across both the legacy
        # and current Hapitas item layouts.
        terms_end_candidates = [
            pos for marker in ("ハピタスご利用前に必ずご確認ください",)
            if (pos := text.find(marker, terms_start + 1)) >= 0
        ]
        terms_end = min(terms_end_candidates) if terms_end_candidates else min(
            len(text), terms_start + 18000
        )
        terms = text[terms_start:terms_end].strip()

        # Hapitas currently has two first-party terms layouts:
        #   legacy: 【ポイント獲得条件】 / 獲得条件達成期限
        #   current StepUp: ▼成果条件 / 【成果受付期間】 /
        #                   【成果調査受付期間】
        # Require both a condition section and an explicit deadline/acceptance
        # section so description text alone can never become publishable terms.
        has_condition_section = bool(re.search(
            r"(?:ポイント獲得条件|(?:^|\s)▼?成果条件(?:\s|$))",
            terms,
        ))
        has_deadline_section = bool(re.search(
            r"(?:成果(?:調査)?受付(?:期間|期限)|獲得条件達成期限|"
            r"広告クリックから[^。\n]{0,80}?[0-9]+\s*日以内|"
            r"インストール(?:日から起算して|後)?[^。\n]{0,80}?[0-9]+\s*日以内)",
            terms,
        ))
        if not (has_condition_section and has_deadline_section):
            raise ValueError("incomplete_offer_terms")

        step_pairs = re.findall(
            r"STEP\s*([0-9]+)\s*[:：]?.*?で\s*([0-9][0-9,]*)\s*pt(?:\s*獲得)?",
            terms,
            re.I,
        )
        step_rewards = []
        if step_pairs:
            step_numbers = [int(step) for step, _ in step_pairs]
            if step_numbers != list(range(1, len(step_numbers) + 1)):
                raise ValueError("incomplete_or_duplicate_steps")
            step_rewards = [int(value.replace(",", "")) for _, value in step_pairs]
            if sum(step_rewards) != displayed_reward:
                raise ValueError("step_total_not_displayed_current_reward")

        title_platform = platform_hint(title)
        if title_platform == "iOS|Android":
            title_platform = ""
        registry_platform = str(reviewed_platform or "").strip()
        if registry_platform and registry_platform not in {"iOS", "Android"}:
            raise ValueError("invalid_reviewed_platform")
        if title_platform and title_platform not in {"iOS", "Android"}:
            title_platform = ""
        if title_platform and registry_platform and title_platform != registry_platform:
            raise ValueError("reviewed_platform_mismatch")
        platform = title_platform or registry_platform
        platform_provenance = (
            "source_title" if title_platform
            else ("reviewed_offer_registry" if registry_platform else "")
        )

        payload = {
            "offerId": offer_id,
            "name": title,
            "platform": platform,
            "platformProvenance": platform_provenance,
            "displayedCurrentRewardPoints": displayed_reward,
            "stepRewardPoints": step_rewards,
            "verifiedCurrentRewardPoints": displayed_reward,
            "verifiedCurrentRewardYen": displayed_reward,
            "rewardUnit": "Hapitas-pt",
            "sourcePointRate": "1pt=1JPY",
            "headerText": re.sub(r"\s+", " ", header).strip(),
            "termsText": terms[:12000],
            "publicationAuthorized": bool(
                publication_authorized
                and platform in {"iOS", "Android"}
                and registry_platform == platform
            ),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "hapitas-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def pointtown_offer_id(url):
    try:
        p = urlparse(str(url or ""))
        port = p.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (p.scheme != "https" or p.hostname not in {"www.pointtown.com", "pointtown.com"}
            or p.username is not None or p.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/item/([0-9]+)/?", p.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    if parse_qs(p.query, keep_blank_values=True):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_pointtown_offer(raw, requested_url, final_url, aliases):
    """Build review-only evidence from a PointTown first-party item detail page."""
    try:
        offer_id = pointtown_offer_id(requested_url)
        if pointtown_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if pointtown_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        title = evidence_text(one(doc.find(tag="h1")))
        title_match_provenance = ""
        if target_present(title, aliases):
            title_match_provenance = "exact_alias"
        else:
            # The current PointTown app-install listing visibly truncates some
            # long anchor labels with an ellipsis even though the linked detail
            # page contains the full title. Accept only a long normalized
            # prefix from an explicitly truncated listing hint, never an
            # arbitrary partial alias.
            title_key = normalized_game_title_key(title)
            for alias in aliases:
                raw_alias = html.unescape(str(alias or "")).strip()
                if raw_alias.endswith("…"):
                    prefix = raw_alias[:-1].rstrip()
                elif raw_alias.endswith("..."):
                    prefix = raw_alias[:-3].rstrip()
                else:
                    continue
                prefix_key = normalized_game_title_key(prefix)
                if len(prefix_key) >= 12 and title_key.startswith(prefix_key):
                    title_match_provenance = "truncated_listing_prefix"
                    break
            if not title_match_provenance:
                raise ValueError("offer_title_mismatch")

        text = visible_text(raw)
        if not re.search(r"1\s*ポイント\s*[=＝]\s*1\s*円", text):
            raise ValueError("unit_conversion_review_required")

        title_pos = text.find(title)
        if title_pos < 0:
            raise ValueError("missing_offer_header")
        condition_pos = text.find("ポイント獲得条件", title_pos)
        if condition_pos < 0:
            raise ValueError("missing_offer_header_boundary")
        header = text[title_pos:condition_pos]

        boundary_positions = [
            pos for token in ("初回利用限定", "友達紹介", "ポイント獲得時期", "予定ポイント反映")
            if (pos := header.find(token)) >= 0
        ]
        reward_region = header[:min(boundary_positions)] if boundary_positions else header[:1200]
        if re.search(
            r"で\s*[0-9][0-9,]*\s+[0-9][0-9,]*(?:\s|$)",
            reward_region,
        ):
            raise ValueError("missing_or_ambiguous_displayed_reward")
        reward_matches = re.findall(
            r"で\s*([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*(?![%0-9])",
            reward_region,
        )
        rewards = [
            int(value.replace(",", ""))
            for value in reward_matches
            if 0 < int(value.replace(",", "")) <= 5_000_000
        ]
        unique_rewards = sorted(set(rewards))
        if len(unique_rewards) != 1:
            raise ValueError("missing_or_ambiguous_displayed_reward")
        reward_points = unique_rewards[0]

        terms_start = text.find("ポイント獲得条件", title_pos)
        service_start = text.find("サービスの説明", terms_start)
        if terms_start < 0 or service_start < 0 or service_start <= terms_start:
            raise ValueError("incomplete_offer_terms")
        terms = text[terms_start:service_start].strip()
        if not any(marker in terms for marker in (
            "獲得条件達成期限",
            "ポイント獲得時期",
            "ポイント獲得条件",
        )):
            raise ValueError("incomplete_offer_terms")

        os_labels = re.findall(
            r"(?<![A-Za-z])(iOS|Android)(?![A-Za-z])",
            title + " " + terms[:1500],
            re.I,
        )
        normalized_os = {"ios": "iOS", "android": "Android"}
        platforms = sorted({normalized_os[value.casefold()] for value in os_labels})
        platform = platforms[0] if len(platforms) == 1 else ""

        payload = {
            "offerId": offer_id,
            "name": title,
            "titleMatchProvenance": title_match_provenance,
            "platform": platform,
            "verifiedCurrentRewardPoints": reward_points,
            "verifiedCurrentRewardYen": reward_points,
            "rewardUnit": "PointTown-point",
            "sourcePointRate": "1pt=1JPY",
            "headerText": re.sub(r"\s+", " ", header).strip(),
            "termsText": terms[:12000],
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "pointtown-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def ecnavi_offer_id(url):
    try:
        p = urlparse(str(url or ""))
        port = p.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (p.scheme != "https" or p.hostname not in {"ecnavi.jp", "www.ecnavi.jp"}
            or p.username is not None or p.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/ad/([0-9]+)/show/?", p.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    query = parse_qs(p.query, keep_blank_values=True)
    if any(key != "frame" for key in query):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_ecnavi_offer(raw, requested_url, final_url, aliases):
    """Build strict review evidence from the current EC Navi detail page.

    Current EC Navi visible text inserts spaces around thousands separators,
    for example 4 , 500 ( 450 円分 ). Normalize only those numeric separators
    inside the bounded reward header. A reward is accepted only when exactly
    one displayed point candidate converts exactly to the displayed yen
    equivalent at EC Navi's first-party 10pts=1JPY rate. Floor/truncated
    displays such as 96pts -> 9円 therefore remain review-required.
    """
    try:
        offer_id = ecnavi_offer_id(requested_url)
        if ecnavi_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if ecnavi_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        title = evidence_text(one(doc.find(tag="h1")))
        title_match_provenance = ""
        if target_present(title, aliases):
            title_match_provenance = "exact_alias"
        else:
            title_key = normalized_game_title_key(title)
            for alias in aliases:
                alias_key = normalized_game_title_key(html.unescape(str(alias or "")))
                if len(title_key) >= 4 and alias_key.startswith(title_key):
                    title_match_provenance = "listing_context_prefix"
                    break
            if not title_match_provenance:
                raise ValueError("offer_title_mismatch")

        text = visible_text(raw)
        if not re.search(r"10\s*pts?\.?\s*[=＝]\s*1\s*円", text, re.I):
            raise ValueError("unit_conversion_review_required")

        condition_pos = text.find("加算条件")
        if condition_pos < 0:
            raise ValueError("missing_offer_header_boundary")
        title_positions = [
            match.start()
            for match in re.finditer(re.escape(title), text)
            if match.start() < condition_pos
        ]
        if not title_positions:
            raise ValueError("missing_offer_header")
        # The title also occurs in head/meta prose. The final occurrence before
        # the actual 加算条件 is the item header tied to the reward display.
        start = max(title_positions)
        header = text[start:condition_pos]
        reward_region = header[len(title):].strip()

        def compact_numeric_separators(value):
            prior = None
            result = str(value or "")
            while result != prior:
                prior = result
                result = re.sub(
                    r"(?<=\d)\s*,\s*(?=\d{3}(?:\D|$))",
                    ",",
                    result,
                )
            return result

        normalized_reward = compact_numeric_separators(reward_region)
        yen_matches = [
            int(value.replace(",", ""))
            for value in re.findall(
                r"[（(]\s*([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*円分\s*[）)]",
                normalized_reward,
            )
        ]
        if len(set(yen_matches)) != 1:
            raise ValueError("missing_or_ambiguous_yen_equivalent")
        displayed_yen = yen_matches[0]

        yen_marker = re.search(
            r"[（(]\s*[1-9][0-9,]*\s*円分\s*[）)]",
            normalized_reward,
        )
        if yen_marker is None:
            raise ValueError("missing_or_ambiguous_yen_equivalent")
        point_header = normalized_reward[:yen_marker.start()]
        point_candidates = sorted({
            int(value.replace(",", ""))
            for value in re.findall(
                r"(?<![0-9,])([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)(?![0-9,])",
                point_header,
            )
            if 0 < int(value.replace(",", "")) <= 5_000_000
        })
        if not point_candidates:
            raise ValueError("missing_displayed_points")

        exact_candidates = [
            amount for amount in point_candidates
            if amount % 10 == 0 and amount // 10 == displayed_yen
        ]
        if len(exact_candidates) != 1:
            raise ValueError("point_yen_conversion_mismatch")
        current_points = exact_candidates[0]

        condition_start = condition_pos
        detail_start = text.find("加算条件詳細", condition_start)
        if detail_start < 0:
            raise ValueError("incomplete_offer_terms")
        detail_end_candidates = [
            pos for marker in ("注意事項", "共通の注意事項")
            if (pos := text.find(marker, detail_start + 1)) >= 0
        ]
        if not detail_end_candidates:
            raise ValueError("incomplete_offer_terms")
        terms = text[condition_start:min(detail_end_candidates)].strip()
        if "加算時期" not in terms:
            raise ValueError("incomplete_offer_terms")

        os_labels = re.findall(
            r"(?<![A-Za-z])(iOS|Android)(?![A-Za-z])",
            title,
            re.I,
        )
        normalized_os = {"ios": "iOS", "android": "Android"}
        platforms = sorted({normalized_os[value.casefold()] for value in os_labels})
        platform = platforms[0] if len(platforms) == 1 else ""

        payload = {
            "offerId": offer_id,
            "name": title,
            "titleMatchProvenance": title_match_provenance,
            "platform": platform,
            "displayedPointCandidates": point_candidates,
            "displayedYenEquivalent": displayed_yen,
            "verifiedCurrentRewardPoints": current_points,
            "verifiedCurrentRewardYen": displayed_yen,
            "rewardUnit": "ECNavi-pt",
            "sourcePointRate": "10pt=1JPY",
            "headerText": re.sub(r"\s+", " ", header).strip(),
            "termsText": terms[:12000],
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "ecnavi-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}

def amefuri_offer_id(url):
    try:
        p = urlparse(str(url or ""))
        port = p.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (p.scheme != "https" or p.hostname not in {"www.amefri.net", "amefri.net"}
            or p.username is not None or p.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/detail/id/([0-9]+)", p.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    query = parse_qs(p.query, keep_blank_values=True)
    if any(key != "tracking" for key in query):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_amefuri_offer(raw, requested_url, final_url, aliases):
    """Build strict review evidence from the current Amefuri detail layout.

    Amefuri currently exposes both the former/base yen value and the boosted
    current yen value in the first-party offer header. Multi-step offers also
    expose every step in source points. The parser accepts the current reward
    only when the bounded offer header is unambiguous; for multi-step offers the
    summed points must additionally convert exactly at the displayed 10pt=1JPY
    rate and equal the largest displayed yen value.

    This parser is review/ranking evidence only. It never authorizes creation of
    a published row by itself.
    """
    try:
        offer_id = amefuri_offer_id(requested_url)
        if amefuri_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if amefuri_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        heading_matches = []
        for node in doc.find(tag="h1"):
            value = evidence_text(node).strip()
            match = re.fullmatch(
                r"案件詳細[:：]\s*(.+?)\s*でポイントが貯まる",
                value,
            )
            if match:
                heading_matches.append(match.group(1).strip())
        if len(heading_matches) != 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        name = heading_matches[0]
        # Some Amefuri titles arrive double-escaped (for example "&amp;").
        # Normalize entities for identity matching while retaining the exact
        # first-party text shape everywhere else in the fingerprint.
        for _ in range(2):
            decoded = html.unescape(name)
            if decoded == name:
                break
            name = decoded
        if not target_present(name, aliases):
            raise ValueError("offer_title_mismatch")

        text = visible_text(raw)
        if not re.search(r"10\s*pt\s*[=＝]\s*1\s*円", text, re.I):
            raise ValueError("unit_conversion_review_required")

        header_start = text.find("アメフリ経由で登録すると")
        if header_start < 0:
            raise ValueError("missing_offer_header_boundary")
        reward_end_candidates = [
            pos for marker in ("成果条件", "反映目安", "承認目安", "広告提供元")
            if (pos := text.find(marker, header_start + 1)) >= 0
        ]
        if not reward_end_candidates:
            raise ValueError("missing_offer_header_boundary")
        reward_end = min(reward_end_candidates)
        if reward_end <= header_start:
            raise ValueError("missing_offer_header_boundary")
        reward_header = text[header_start:reward_end]

        condition_start = text.find("成果条件", header_start)
        condition_text = ""
        if condition_start >= 0:
            condition_end_candidates = [
                pos for marker in ("反映目安", "承認目安", "広告提供元")
                if (pos := text.find(marker, condition_start + 1)) >= 0
            ]
            condition_end = (
                min(condition_end_candidates)
                if condition_end_candidates
                else min(len(text), condition_start + 1200)
            )
            condition_text = re.sub(
                r"\s+", " ",
                text[condition_start + len("成果条件"):condition_end],
            ).strip()
        if not condition_text:
            raise ValueError("missing_offer_condition")

        displayed_yen = sorted({
            int(value.replace(",", ""))
            for value in re.findall(
                r"(?<![0-9,])([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*円",
                reward_header,
            )
        })
        if not displayed_yen or len(displayed_yen) > 3:
            raise ValueError("ambiguous_displayed_reward")
        current_reward_yen = max(displayed_yen)

        offer_header_end = text.find("公式サイトを確認", reward_end)
        if offer_header_end < 0:
            offer_header_end = min(len(text), reward_end + 6000)
        platform_scope = name + " " + text[header_start:offer_header_end]
        os_labels = re.findall(
            r"(?<![A-Za-z])(iOS|Android)(?![A-Za-z])",
            platform_scope,
            re.I,
        )
        normalized_os = {"ios": "iOS", "android": "Android"}
        platforms = sorted({normalized_os[value.casefold()] for value in os_labels})
        if len(platforms) != 1:
            raise ValueError("ambiguous_offer_platform")
        platform = platforms[0]

        # The current page has a visible StepUp table only for multi-step offers.
        multi_match = re.search(
            r"(?:【|〖|\[)?多段階(?:】|〗|\])?",
            text[reward_end:offer_header_end],
        )
        step_points = []
        reward_mode = "Single"
        if multi_match:
            reward_mode = "StepUp"
            multi_start = reward_end + multi_match.start()
            multi_end_candidates = [
                pos for marker in ("多段階案件は", "ポイント獲得条件", "公式サイトを確認")
                if (pos := text.find(marker, multi_start + 1)) >= 0
            ]
            multi_end = min(multi_end_candidates) if multi_end_candidates else offer_header_end
            if multi_end <= multi_start:
                raise ValueError("missing_multistep_boundary")
            step_text = text[multi_start:multi_end]
            step_points = [
                int(value.replace(",", ""))
                for value in re.findall(
                    r"ステップ\s*[0-9]+.*?認証済\s*([0-9][0-9,]*)\s*pt\b",
                    step_text,
                    re.I,
                )
            ]
            if len(step_points) < 2:
                raise ValueError("incomplete_multistep_rewards")
            if any(value <= 0 for value in step_points):
                raise ValueError("invalid_multistep_reward")
            step_total_points = sum(step_points)
            if step_total_points % 10 != 0:
                raise ValueError("step_total_conversion_mismatch")
            if step_total_points // 10 != current_reward_yen:
                raise ValueError("step_total_not_displayed_current_reward")
        else:
            step_total_points = current_reward_yen * 10

        terms_start = text.find("ポイント獲得条件", offer_header_end)
        if terms_start < 0:
            terms_start = text.find("ポイント獲得条件", reward_end)
        if terms_start < 0:
            raise ValueError("incomplete_offer_terms")
        terms_end_candidates = [
            pos for marker in (
                "友達紹介のダウン報酬対象外です。",
                "広告案件のポイント付与に関するご質問",
                "他のユーザーが取り組んでいる案件もチェック",
            )
            if (pos := text.find(marker, terms_start + 1)) >= 0
        ]
        terms_end = min(terms_end_candidates) if terms_end_candidates else min(
            len(text), terms_start + 12000
        )
        terms = text[terms_start:terms_end].strip()
        if len(terms) > 12000:
            terms = terms[:12000]

        if "ポイント獲得条件" not in terms:
            raise ValueError("incomplete_offer_terms")
        if not any(marker in terms for marker in (
            "▼却下条件", "■却下条件", "【却下条件】", "却下条件",
        )):
            raise ValueError("incomplete_offer_terms")

        # Amefuri currently uses two valid condition layouts. Some networks put
        # the achievement conditions in the StepUp table / header and leave the
        # terms pane for investigation and rejection rules. Others repeat a
        # dedicated 承認条件/成果条件 section in the terms pane. Never infer a
        # condition from generic prose: a StepUp must have parsed steps, while a
        # single offer must expose a non-generic bounded 成果条件 value.
        terms_has_condition = any(marker in terms for marker in (
            "▼承認条件", "■承認条件", "【成果条件】", "成果地点①",
            "新規アプリインストール後",
        ))
        if reward_mode == "StepUp":
            if not step_points:
                raise ValueError("incomplete_offer_terms")
        elif condition_text in {"", "条件達成"} and not terms_has_condition:
            raise ValueError("incomplete_offer_terms")

        deadline_scope = terms + " " + condition_text
        if reward_mode == "StepUp":
            deadline_scope += " " + step_text
        achievement_deadline_explicit = bool(re.search(
            r"(?:成果到達期限[:：]?[^0-9]{0,20}[0-9]+\s*日以内|"
            r"達成期限[:：]?\s*[0-9]+\s*日以内|"
            r"広告クリックから[^。]{0,100}?[0-9]+\s*日以内|"
            r"インストール[^。]{0,100}?[0-9]+\s*(?:日|日間)(?:以内)?|"
            r"[0-9]+\s*日間\s*[（(][0-9]+\s*時間[）)]\s*以内|"
            r"[0-9]+\s*日以内)",
            deadline_scope,
        ))

        verified_points = (
            sum(step_points) if step_points else current_reward_yen * 10
        )
        if verified_points != current_reward_yen * 10:
            raise ValueError("yen_point_mismatch")

        payload = {
            "offerId": offer_id,
            "name": name,
            "platform": platform,
            "rewardMode": reward_mode,
            "displayedRewardYenCandidates": displayed_yen,
            "displayedCurrentRewardYen": current_reward_yen,
            "conditionText": condition_text,
            "achievementDeadlineExplicit": achievement_deadline_explicit,
            "stepRewardPoints": step_points,
            "stepTotalPoints": sum(step_points) if step_points else None,
            "verifiedCurrentRewardPoints": verified_points,
            "verifiedCurrentRewardYen": current_reward_yen,
            "rewardUnit": "JPY-equivalent",
            "sourcePointRate": "10pt=1JPY",
            "headerText": re.sub(r"\s+", " ", reward_header).strip(),
            "termsText": terms,
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "amefuri-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}

def moppy_offer_id(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname != "pc.moppy.jp"
            or p.username is not None or p.password is not None or p.port not in {None, 443}
            or p.path != "/ad/detail.php"):
        raise ValueError("unexpected_offer_url")
    query = parse_qs(p.query, keep_blank_values=True)
    if any(key not in {"site_id", "s_id", "track_ref"} for key in query):
        raise ValueError("ambiguous_offer_identity")
    track_ref = query.get("track_ref", [])
    if track_ref and (len(track_ref) != 1 or track_ref[0] != "category"):
        raise ValueError("ambiguous_offer_identity")
    values = []
    for key in ("site_id", "s_id"):
        values.extend(query.get(key) or [])
    if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
        raise ValueError("ambiguous_offer_identity")
    return values[0]


def inspect_moppy_offer(raw, requested_url, final_url, aliases):
    """Parse current first-party Moppy detail evidence for ranking/review.

    Moppy's app catalog appends the reviewed track_ref=category navigation
    parameter to stable s_id detail identities. The current detail page exposes
    one dedicated current-point element plus one bounded terms section. StepUp
    offers that delegate tier conditions to POINT GET remain non-ranking.
    """
    try:
        offer_id = moppy_offer_id(requested_url)
        if moppy_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        titles = [evidence_text(node) for node in doc.find(tag="h1")
                  if evidence_text(node)]
        titles = list(dict.fromkeys(titles))
        if len(titles) != 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        title = titles[0]

        if not target_present(title, aliases):
            title_key = normalized_game_title_key(title)
            matched = False
            for alias in aliases:
                alias_key = normalized_game_title_key(alias)
                # Current category cards can append condition/reward text after
                # the exact detail title. Accept only that one-way prefix shape.
                if len(title_key) >= 4 and alias_key.startswith(title_key):
                    matched = True
                    break
            if not matched:
                raise ValueError("offer_title_mismatch")

        title_platforms = sorted(set(re.findall(r"(iOS|Android)", title, re.I)))
        norm = {"ios": "iOS", "android": "Android"}
        platform_values = sorted({norm[x.casefold()] for x in title_platforms})
        platform = platform_values[0] if len(platform_values) == 1 else "unspecified"

        # Reward must come from the dedicated current-point element only.
        point_values = []
        for node in doc.find(tag="em", cls="a-item__point--now"):
            value = evidence_text(node)
            match = re.fullmatch(
                r"\s*([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)\s*P\s*",
                value,
            )
            if match:
                point_values.append(int(match.group(1).replace(",", "")))
        unique_rewards = sorted(set(point_values))
        if len(unique_rewards) != 1:
            raise ValueError("missing_or_ambiguous_current_reward")
        reward_points = unique_rewards[0]
        if not 0 < reward_points <= 5_000_000:
            raise ValueError("invalid_reward")

        # The reviewed current app page keeps the actual campaign rules inside
        # one tabbed main section. Binding to this container avoids generic
        # Moppy help text elsewhere on the page.
        terms_sections = []
        for node in doc.find(tag="section"):
            classes = set(node.attrs.get("class", "").split())
            if not {"m-section--main", "m-tabslider"} <= classes:
                continue
            value = evidence_text(node)
            has_condition = any(marker in value for marker in (
                "▼ポイント獲得条件", "■ポイント獲得条件", "■獲得条件",
                "【獲得条件】", "【獲得対象】", "成果受付期限",
                "新規アプリインストール後", "新規インストール後",
            ))
            if (
                has_condition
                and "広告概要" in value
                and any(marker in value for marker in (
                    "却下条件", "注意事項", "対象外", "ご注意点"
                ))
                and any(marker in value for marker in (
                    "お問い合わせ", "お問合せ", "広告主", "スポンサーサイト",
                    "成果調査受付期限",
                ))
            ):
                terms_sections.append(value)
        unique_sections = list(dict.fromkeys(terms_sections))
        if len(unique_sections) != 1:
            raise ValueError("incomplete_or_ambiguous_offer_terms")

        section_text = unique_sections[0]
        terms_end = section_text.find("広告概要")
        starts = [
            section_text.find(marker)
            for marker in (
                "▼ポイント獲得条件",
                "■ポイント獲得条件",
                "■獲得条件",
                "【獲得条件】",
                "【獲得対象】",
            )
        ]
        starts = [pos for pos in starts if 0 <= pos < terms_end]
        if starts:
            terms_start = min(starts)
        else:
            pr_marker = section_text.find("[PR]")
            strong_unheaded = (
                any(marker in section_text[:terms_end] for marker in (
                    "成果受付期限", "成果調査受付期限"
                ))
                and any(marker in section_text[:terms_end] for marker in (
                    "新規アプリインストール後", "新規インストール後",
                    "成果となります", "報酬獲得となります",
                ))
            )
            if pr_marker >= 0 and strong_unheaded:
                terms_start = pr_marker
            else:
                raise ValueError("incomplete_offer_terms")
        if terms_end <= terms_start:
            raise ValueError("incomplete_offer_terms")
        terms = re.sub(r"\s+", " ", section_text[terms_start:terms_end]).strip()
        if len(terms) < 120:
            raise ValueError("incomplete_offer_terms")

        if not any(marker in terms for marker in (
            "却下条件", "注意事項", "成果対象外", "獲得対象外", "ポイント対象外",
        )):
            raise ValueError("incomplete_offer_terms")
        if not any(marker in terms for marker in (
            "お問い合わせ", "お問合せ", "広告主", "スポンサーサイト",
        )):
            raise ValueError("incomplete_offer_terms")

        downstream_required = bool(re.search(r"POINT\s*GET", terms, re.I))

        payload = {
            "offerId": offer_id,
            "name": title,
            "platform": platform,
            "displayedRewardPoints": reward_points,
            "displayedRewardYen": reward_points,
            "verifiedCurrentRewardYen": reward_points,
            "rewardUnit": "Moppy-P",
            "sourcePointRate": "1P=1JPY",
            "downstreamTermsRequired": downstream_required,
            "termsText": terms[:12000],
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "moppy-detail-review-v3",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}



def gendama_offer_id(url):
    """Return a stable numeric Gendama identity for reviewed legacy/current URLs."""
    try:
        p = urlparse(str(url or ""))
        port = p.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (p.scheme != "https" or p.hostname != "www.gendama.jp"
            or p.username is not None or p.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")

    query = parse_qs(p.query, keep_blank_values=True)
    if p.path == "/sp/client_detail":
        values = query.get("cd_client", [])
        if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
            raise ValueError("ambiguous_offer_identity")
        if any(key not in {"cd_client", "rt"} for key in query):
            raise ValueError("unexpected_offer_url")
        for value in query.get("rt", []):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", value or ""):
                raise ValueError("unexpected_offer_url")
        return values[0]

    match = re.fullmatch(r"/service/item/([0-9]+)", p.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    if any(key != "frame" for key in query):
        raise ValueError("unexpected_offer_url")
    return match.group(1)


def inspect_gendama_offer(raw, requested_url, final_url, aliases):
    """Extract ranking-only evidence from current/legacy Gendama detail pages.

    Current mobile pages are Shift_JIS and expose an exact pt + yen-equivalent
    pair inside one offer card. Reward values are never inferred from a base
    conversion. Platform remains unknown unless the exact first-party title,
    condition, or listing alias explicitly names iOS/Android.
    """
    try:
        offer_id = gendama_offer_id(requested_url)
        if gendama_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        text = visible_text(raw)
        if "ページが見つかりません" in text or "掲載終了" in text:
            return {"state": "unavailable", "reason": "source_offer_unavailable",
                    "offerId": offer_id}

        title_nodes = doc.find(tag="title")
        title_text = evidence_text(one(title_nodes)) if title_nodes else ""
        current_name = re.sub(
            r"\s*の口コミ・評判[｜|].*$", "", title_text
        ).strip()
        h1_values = [evidence_text(node) for node in doc.find(tag="h1")
                     if evidence_text(node)]
        name = current_name or (h1_values[0] if len(h1_values) == 1 else "")
        if not name:
            raise ValueError("missing_offer_title")
        if not target_present(name, aliases):
            raise ValueError("offer_title_mismatch")

        pairs = {
            (int(points.replace(",", "")), int(yen.replace(",", "")))
            for points, yen in re.findall(
                r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt\s*[（(]\s*"
                r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*円相当\s*[）)]",
                text, re.I
            )
        }
        if len(pairs) != 1:
            raise ValueError("missing_or_ambiguous_yen_equivalent")
        reward_points, reward_yen = next(iter(pairs))
        if not (0 < reward_points < 5_000_000 and 0 < reward_yen < 1_000_000):
            raise ValueError("invalid_reward")

        condition_candidates = [
            evidence_text(node) for node in doc.find(cls="service_content")
            if 2 <= len(evidence_text(node)) <= 500
        ]
        if len(set(condition_candidates)) == 1:
            condition = condition_candidates[0]
        else:
            match = re.search(r"ポイント獲得条件\s*[（(]\s*(.+?)\s*[）)]", text)
            condition = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
        if len(condition) < 2:
            raise ValueError("missing_offer_condition")

        term_candidates = []
        positive_markers = (
            "成果受付期限", "成果調査受付期限", "ポイント付与条件",
            "ポイント付与受付期間", "獲得条件", "お問い合わせ受付期限",
        )
        rejection_markers = (
            "成果対象外", "却下条件", "獲得対象外", "注意事項", "ご注意点",
        )
        support_markers = (
            "広告主", "スポンサーサイト", "成果調査", "ポイント付与調査",
            "お問い合わせ", "問合せ",
        )
        for node in doc.find(cls="service_detail_p"):
            value = evidence_text(node)
            reviewed_shape = (
                any(marker in value for marker in positive_markers)
                and any(marker in value for marker in rejection_markers)
                and any(marker in value for marker in support_markers)
            )
            if len(value) >= 120 and reviewed_shape:
                term_candidates.append(value)
        unique_terms = list(dict.fromkeys(term_candidates))
        if len(unique_terms) != 1:
            raise ValueError("incomplete_or_ambiguous_offer_terms")
        terms = unique_terms[0]

        platform = platform_hint(" ".join([name, condition, *[
            str(alias or "") for alias in aliases
        ]]))
        if platform not in {"iOS", "Android", "iOS|Android"}:
            platform = "unknown"

        payload = {
            "offerId": offer_id,
            "name": name,
            "platform": platform,
            "displayedRewardPoints": reward_points,
            "displayedRewardYen": reward_yen,
            "rewardUnit": "JPY-equivalent",
            "condition": condition,
            "termsText": terms[:12000],
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")).hexdigest()
        return {"state": "parsed", "parserVersion": "gendama-detail-review-v2",
                **payload, "evidenceFingerprint": fingerprint}
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}

def powl_offer_id(url):
    try:
        parsed = urlparse(str(url or ""))
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (parsed.scheme != "https" or parsed.hostname not in {"web.powl.jp"}
            or parsed.username is not None or parsed.password is not None
            or port not in {None, 443}):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/reward/([0-9]+)/?", parsed.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    if parse_qs(parsed.query, keep_blank_values=True):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_powl_offer(raw, requested_url, final_url, aliases):
    """Build ranking-only evidence from Powl's current first-party reward card.

    The visible total is duplicated for responsive layouts inside one
    reward-parent container. Require every matching p.pt node to agree and
    ignore tier rewards, recommendations, and other numeric prose outside that
    container. Powl's reviewed base scale is 10pt=1JPY; fractional-yen totals
    are preserved to one decimal place. Publication stays disabled.
    """
    try:
        offer_id = powl_offer_id(requested_url)
        if powl_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if powl_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        title_text = evidence_text(one(doc.find(tag="title")))
        name = re.sub(r"\s*[|｜]\s*Powl\s*$", "", title_text, flags=re.I).strip()
        if not name:
            raise ValueError("missing_offer_title")
        if not target_present(name, aliases):
            name_key = normalized_game_title_key(name)
            matched = False
            for alias in aliases:
                alias_key = normalized_game_title_key(html.unescape(str(alias or "")))
                if len(name_key) >= 4 and alias_key.startswith(name_key):
                    matched = True
                    break
            if not matched:
                raise ValueError("offer_title_mismatch")

        reward_parent = one(doc.find(cls="reward-parent"))
        point_values = []
        for node in reward_parent.find(cls="pt"):
            value = evidence_text(node).replace(" ", "")
            match = re.fullmatch(
                r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)pt",
                value,
                re.I,
            )
            if match:
                amount = int(match.group(1).replace(",", ""))
                if 0 < amount <= 5_000_000:
                    point_values.append(amount)
        unique_points = sorted(set(point_values))
        if len(unique_points) != 1:
            raise ValueError("missing_or_ambiguous_displayed_reward")
        reward_points = unique_points[0]

        condition = evidence_text(one(reward_parent.find(cls="results")))
        if len(condition) < 4:
            raise ValueError("missing_offer_condition")

        text = visible_text(raw)
        title_pos = text.find(name)
        terms_start = text.find("ポイント獲得条件", max(0, title_pos))
        description_start = text.find("広告の説明", terms_start) if terms_start >= 0 else -1
        if terms_start < 0 or description_start <= terms_start:
            raise ValueError("incomplete_offer_terms")
        terms = text[terms_start:description_start].strip()
        if len(terms) < 80 or not any(marker in terms for marker in (
            "承認条件", "成果条件", "新規インストール", "新規アプリインストール"
        )):
            raise ValueError("incomplete_offer_terms")
        if not any(marker in terms for marker in (
            "却下条件", "注意事項", "成果のお問い合わせ", "成果のお問合せ"
        )):
            raise ValueError("incomplete_offer_terms")

        platform = platform_hint(name)
        if platform not in {"iOS", "Android"}:
            raise ValueError("ambiguous_offer_platform")

        reward_yen = reward_points / 10
        if reward_yen.is_integer():
            reward_yen = int(reward_yen)
        else:
            reward_yen = round(reward_yen, 1)

        payload = {
            "offerId": offer_id,
            "name": name,
            "platform": platform,
            "displayedRewardPoints": reward_points,
            "verifiedCurrentRewardYen": reward_yen,
            "rewardUnit": "Powl-pt",
            "sourcePointRate": "10pt=1JPY",
            "conditionText": condition,
            "termsText": terms[:12000],
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "powl-detail-review-v1",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def kurashiru_reward_offer_id(url):
    """Return the stable numeric identity for current Kurashiru Reward ad URLs."""
    try:
        parsed = urlparse(str(url or ""))
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("unexpected_offer_url")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.rewards.kurashiru.com", "rewards.kurashiru.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError("unexpected_offer_url")
    match = re.fullmatch(r"/ads?/([0-9]+)/?", parsed.path or "")
    if not match:
        raise ValueError("unexpected_offer_url")
    if parse_qs(parsed.query, keep_blank_values=True):
        raise ValueError("ambiguous_offer_identity")
    return match.group(1)


def inspect_kurashiru_reward_offer(raw, requested_url, final_url, aliases):
    """Parse current first-party Kurashiru Reward evidence for ranking only."""
    try:
        offer_id = kurashiru_reward_offer_id(requested_url)
        if kurashiru_reward_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [
            node for node in doc.find(tag="link")
            if "canonical" in node.attrs.get("rel", "").split()
        ]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if kurashiru_reward_offer_id(canonical) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        titles = [
            evidence_text(node).strip()
            for node in doc.find(tag="h1")
            if evidence_text(node).strip()
        ]
        titles = list(dict.fromkeys(titles))
        if len(titles) != 1:
            raise ValueError("missing_or_ambiguous_offer_title")
        name = titles[0]

        if not target_present(name, aliases):
            name_key = normalized_game_title_key(name)
            matched = False
            for alias in aliases:
                alias_key = normalized_game_title_key(html.unescape(str(alias or "")))
                if len(name_key) >= 4 and (
                    alias_key.startswith(name_key) or name_key.startswith(alias_key)
                ):
                    matched = True
                    break
            if not matched:
                raise ValueError("offer_title_mismatch")

        # Bind current coins to the reviewed red current-reward span inside the
        # first-party "コイン獲得条件" box. Old promotional values use line-through.
        current_values = set()
        reward_boxes = []
        for node in doc.find(tag="div"):
            value = evidence_text(node)
            if "コイン獲得条件" not in value or "コイン還元" not in value:
                continue
            scoped = []
            for span in node.find(tag="span"):
                classes = set(span.attrs.get("class", "").split())
                if "line-through" in classes:
                    continue
                if not {"text-rs-red-main", "text-2xl"} <= classes:
                    continue
                raw_value = evidence_text(span)
                if re.fullmatch(r"[1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*", raw_value):
                    scoped.append(int(raw_value.replace(",", "")))
            if scoped:
                reward_boxes.append(value)
                current_values.update(scoped)

        if len(current_values) != 1:
            raise ValueError("missing_or_ambiguous_displayed_reward")
        reward_coins = next(iter(current_values))
        if not 0 < reward_coins <= 20_000_000:
            raise ValueError("invalid_reward")

        text = visible_text(raw)
        if not re.search(r"100\s*コイン\s*[=＝]\s*1\s*円\s*相当", text):
            raise ValueError("missing_current_coin_rate")

        reward_yen = reward_coins / 100
        if reward_yen.is_integer():
            reward_yen = int(reward_yen)
        else:
            reward_yen = round(reward_yen, 2)

        # Use the smallest visible DOM block containing the complete rule set,
        # avoiding global navigation/help text and unrelated recommendation cards.
        terms_candidates = []
        for node in doc.find(tag="div") + doc.find(tag="section"):
            value = evidence_text(node)
            if not 180 <= len(value) <= 20000:
                continue
            if "注意事項" not in value:
                continue
            if not any(marker in value for marker in (
                "成果受付期限", "承認条件", "成果条件", "成果となります",
            )):
                continue
            if not any(marker in value for marker in (
                "却下条件", "成果対象外", "ポイント付与対象外", "報酬付与対象外",
            )):
                continue
            if not any(marker in value for marker in (
                "広告主", "スポンサーサイト", "成果調査", "お問い合わせ", "お問合せ",
            )):
                continue
            terms_candidates.append(value)
        if not terms_candidates:
            raise ValueError("incomplete_offer_terms")
        terms = min(terms_candidates, key=len)
        terms = re.sub(r"\s+", " ", terms).strip()

        condition = ""
        for box in reward_boxes:
            match = re.search(
                r"コイン獲得条件\s+(.{2,500}?)\s+で\s+(?:MAX\s+)?",
                box,
            )
            if match:
                condition = re.sub(r"\s+", " ", match.group(1)).strip()
                break
        if len(condition) < 2:
            raise ValueError("missing_offer_condition")

        platform = platform_hint(" ".join([name, *[str(alias or "") for alias in aliases]]))
        if platform not in {"iOS", "Android"}:
            platform = "unknown"

        payload = {
            "offerId": offer_id,
            "name": name,
            "platform": platform,
            "verifiedCurrentRewardCoins": reward_coins,
            "verifiedCurrentRewardYen": reward_yen,
            "rewardUnit": "Kurashiru-coin",
            "sourcePointRate": "100coin=1JPY",
            "conditionText": condition,
            "termsText": terms[:12000],
            "downstreamTermsRequired": False,
            "publicationAuthorized": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "state": "parsed",
            "parserVersion": "kurashiru-reward-detail-review-v2",
            **payload,
            "evidenceFingerprint": fingerprint,
        }
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def inspect_detail(url, source, aliases, fetcher=None, provider_label_registry=None):
    raw, final_url = (fetcher or fetch_first_party)(url, source)
    structured_parsers = {
        "warau": inspect_warau_offer,
        "chobirich": inspect_chobirich_offer,
        "coincome": inspect_coincome_offer,
        "hapitas": inspect_hapitas_offer,
        "point_town": inspect_pointtown_offer,
        "ec_navi": inspect_ecnavi_offer,
        "amefuri": inspect_amefuri_offer,
        "moppy": inspect_moppy_offer,
        "gendama": inspect_gendama_offer,
        "powl": inspect_powl_offer,
        "kurashiru_reward": inspect_kurashiru_reward_offer,
    }
    if source.get("id") in structured_parsers:
        if source.get("id") == "hapitas":
            try:
                offer_id = hapitas_offer_id(url)
            except ValueError:
                offer_id = ""
            platform_registry = source.get("reviewed_platform_by_offer_id") or {}
            reviewed_platform = platform_registry.get(offer_id, "")
            evidence = inspect_hapitas_offer(
                raw, url, final_url, aliases,
                reviewed_platform=reviewed_platform,
                publication_authorized=(
                    source.get("reviewed_reward_refresh_enabled") is True
                    and bool(reviewed_platform)
                ),
            )
        else:
            evidence = structured_parsers[source["id"]](raw, url, final_url, aliases)

        if source.get("id") == "moppy" and evidence.get("state") == "parsed":
            labels = provider_label_registry
            if labels is None:
                try:
                    domains = load_offerwall_provider_registry()
                    labels = load_offerwall_provider_label_registry(
                        OFFERWALL_PROVIDERS, domains
                    )
                except (OSError, ValueError, TypeError):
                    labels = {}
            provider_candidates = offerwall_provider_candidates_from_text(
                evidence.get("termsText", ""), labels or {}
            )
            if provider_candidates:
                evidence = dict(evidence)
                evidence["downstreamTermsRequired"] = True
                evidence["downstreamProviderCandidates"] = provider_candidates
        if (source.get("id") == "warau" and evidence.get("state") == "parsed"
                and provider_label_registry):
            provider_candidates = offerwall_provider_candidates_from_text(
                evidence.get("name", ""), provider_label_registry
            )
            if len(provider_candidates) == 1:
                evidence = dict(evidence)
                evidence["providerId"] = provider_candidates[0]["providerId"]
                evidence["provider"] = provider_candidates[0]["providerName"]
            elif len(provider_candidates) > 1:
                evidence = dict(evidence)
                evidence["providerCandidates"] = provider_candidates
        return {"url": final_url, "sourceEvidence": evidence,
                "targetPresent": evidence["state"] == "parsed",
                "platform": evidence.get("platform", "")}
    text = visible_text(raw)
    if not target_present(text, aliases):
        return {"url": final_url, "targetPresent": False, "platform": "", "_text": text}
    strong, weak, generic = reward_candidates(text)
    return {
        "url": final_url,
        "targetPresent": True,
        "platform": platform_hint(text),
        "strongCandidates": strong[-8:],
        "weakCandidates": weak[-8:],
        "genericCandidates": generic[-12:],
        "_text": text,
    }


def published_row_fingerprint(row):
    """Bind approval to all published fields except the renewable check date."""
    values = {k: v for k, v in row.items() if k != "updatedAt"}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()


def load_refresh_approvals():
    # This is a reviewed, version-controlled input, never generated from a run's
    # review queue. Missing approval is normal; malformed approval fails closed.
    path = POLICY.with_name("approved_offer_baselines.json")
    if not path.exists():
        return {}
    value = load_json(path)
    if (not isinstance(value, dict) or type(value.get("schemaVersion")) is not int
            or value["schemaVersion"] != 1 or not isinstance(value.get("approvals"), list)):
        raise ValueError("invalid_approval_registry")
    approvals = {}
    for item in value["approvals"]:
        if not isinstance(item, dict) or not isinstance(item.get("offerKey"), str) or not item["offerKey"]:
            raise ValueError("invalid_approval_entry")
        if item["offerKey"] in approvals:
            raise ValueError("duplicate_approval_key")
        approvals[item["offerKey"]] = item
    return approvals


def approved_refresh_reason(row, evidence, approval, checked_at):
    """Return a hold reason, or None for an exact, unexpired approved baseline.

    Approval is an explicit maintainer decision about the full source conditions
    AND the published summary. Parsing or equality alone must never create it.
    """
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return "baseline_approval_required"
    if row.get("site") != "warau" or row.get("verified") != "true":
        return "published_row_not_verified"
    if evidence.get("state") != "parsed" or evidence.get("parserVersion") != "warau-stepup-v1":
        return "source_evidence_not_supported"
    if (approval.get("offerKey") != row.get("offerKey") or approval.get("game") != row.get("game")
            or approval.get("source") != "warau" or not isinstance(approval.get("reviewedBy"), str)
            or not approval["reviewedBy"].strip()):
        return "approval_identity_mismatch"
    try:
        if (warau_offer_id(row["url"]) != evidence.get("offerId")
                or warau_offer_id(row["sourceUrl"]) != evidence.get("offerId")):
            return "approval_identity_mismatch"
        now = datetime.fromisoformat(checked_at)
        reviewed = datetime.fromisoformat(approval["reviewedAt"])
        expires = datetime.fromisoformat(approval["expiresAt"])
        if any(x.tzinfo is None for x in (now, reviewed, expires)) or not reviewed <= now < expires:
            return "approval_expired_or_invalid_time"
        deadline = row.get("deadline", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline):
            if datetime.fromisoformat(deadline).date() < now.astimezone(timezone(timedelta(hours=9))).date():
                return "published_deadline_expired"
    except (KeyError, ValueError, TypeError):
        return "approval_expired_or_invalid_identity"
    if row.get("platform") != evidence.get("platform"):
        return "approved_platform_changed"
    if approval.get("publishedRowFingerprint") != published_row_fingerprint(row):
        return "published_row_changed_since_approval"
    if (approval.get("parserVersion") != evidence.get("parserVersion")
            or approval.get("evidenceFingerprint") != evidence.get("evidenceFingerprint")):
        return "source_terms_changed_since_approval"
    # Reviewed Warau base face-value conversion only; not redemption fees/miles.
    rate = approval.get("unitConversion")
    if (not isinstance(rate, dict) or rate.get("sourceUnit") != "pt" or rate.get("targetUnit") != "JPY"
            or type(rate.get("yenPerPoint")) is not int or rate["yenPerPoint"] != 1
            or rate.get("evidenceUrl") != "https://www.warau.jp/help/qa/128/"
            or evidence.get("rewardUnit") != "pt"):
        return "unit_conversion_review_required"
    reward = str(row.get("reward", ""))
    if not re.fullmatch(r"[1-9][0-9]*", reward) or int(reward) != evidence.get("rewardPoints"):
        return "approved_reward_changed"
    return None


def load_offerwall_provider_registry(path=OFFERWALL_PROVIDERS):
    """Return exact presence-domain -> reviewed provider metadata.

    The provider registry is review metadata only. Unsupported or unsafe
    retrieval contracts are rejected rather than normalized heuristically.
    """
    if not path.exists():
        return {}
    value = load_json(path)
    if (not isinstance(value, dict) or value.get("schemaVersion") != 1
            or not isinstance(value.get("providers"), list)):
        raise ValueError("invalid_offerwall_provider_registry")
    by_domain = {}
    provider_ids = set()
    for item in value["providers"]:
        if not isinstance(item, dict):
            raise ValueError("invalid_offerwall_provider_entry")
        provider_id = item.get("id")
        if (not isinstance(provider_id, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", provider_id)
                or provider_id in provider_ids):
            raise ValueError("invalid_or_duplicate_offerwall_provider_id")
        provider_ids.add(provider_id)
        if (item.get("retrievalMode") != "presence_only"
                or item.get("followExternalLinks") is not False
                or item.get("persist") != "provider_domain_only"):
            raise ValueError("unsafe_offerwall_provider_contract")
        domains = item.get("presenceDomains")
        if not isinstance(domains, list) or not domains:
            raise ValueError("missing_offerwall_provider_domains")
        for raw_domain in domains:
            domain = str(raw_domain or "").lower().strip()
            if (not re.fullmatch(r"[a-z0-9.-]+", domain)
                    or domain.startswith(".") or domain.endswith(".")
                    or ".." in domain or domain in by_domain):
                raise ValueError("invalid_or_duplicate_offerwall_provider_domain")
            by_domain[domain] = {
                "providerId": provider_id,
                "providerName": str(item.get("name") or provider_id),
                "domain": domain,
                "retrievalMode": "presence_only",
            }
    return by_domain


def offerwall_provider_candidates(domains, registry):
    candidates = []
    for domain in domains:
        item = registry.get(domain)
        if item is not None:
            candidates.append(dict(item))
    return candidates


def load_offerwall_provider_label_registry(path, domain_registry):
    """Build reviewed first-party text labels -> provider metadata.

    Labels are optional review hints. They never authorize a provider request.
    """
    if not path.exists():
        return {}
    value = load_json(path)
    providers = value.get("providers") if isinstance(value, dict) else None
    if not isinstance(providers, list):
        raise ValueError("invalid_offerwall_provider_registry")
    labels = {}
    for item in providers:
        raw_labels = item.get("firstPartyLabels") or []
        if not raw_labels:
            continue
        if not isinstance(raw_labels, list):
            raise ValueError("invalid_offerwall_provider_labels")
        domains = item.get("presenceDomains") or []
        metadata = next((domain_registry.get(str(d).lower().strip()) for d in domains
                         if domain_registry.get(str(d).lower().strip()) is not None), None)
        if metadata is None:
            raise ValueError("provider_label_without_reviewed_domain")
        for raw_label in raw_labels:
            label = normalized_text(raw_label)
            if len(label) < 4 or label in labels:
                raise ValueError("invalid_or_duplicate_offerwall_provider_label")
            labels[label] = dict(metadata)
    return labels


def offerwall_provider_candidates_from_text(text, label_registry):
    hay = normalized_text(text)
    candidates = []
    seen = set()
    for label, metadata in label_registry.items():
        provider_id = metadata.get("providerId")
        if label in hay and provider_id not in seen:
            seen.add(provider_id)
            candidates.append(dict(metadata))
    return candidates


def build_existing_game_candidate_queue(review_items, checked_at):
    """Persist only bounded, review-safe existing-game price/offer candidates."""
    allowed_reasons = {
        "reward_change_candidate",
        "moppy_shell_reward_change_candidate",
        "first_party_existing_game_new_offer_candidate",
        "first_party_existing_game_reward_change_candidate",
        "first_party_existing_game_reward_verified",
    }
    items = []
    seen = set()
    for raw in review_items or []:
        if not isinstance(raw, dict):
            continue
        reason = str(raw.get("reason") or "")
        if reason not in allowed_reasons:
            continue
        source = str(raw.get("source") or "")
        game = str(raw.get("game") or "")
        url = str(raw.get("url") or "")
        identity = offer_identity_key(url, source) if url else ""
        key = (game, source, identity or exact_url_key(url), reason)
        if key in seen:
            continue
        seen.add(key)

        evidence = raw.get("sourceEvidence") if isinstance(raw.get("sourceEvidence"), dict) else {}
        item = {
            "game": game,
            "source": source,
            "url": url,
            "offerIdentity": identity,
            "reason": reason,
            "storedReward": raw.get("storedReward"),
            "detectedReward": raw.get("detectedReward"),
            "platformHint": raw.get("platformHint") or evidence.get("platform") or "",
            "parserVersion": str(evidence.get("parserVersion") or ""),
            "evidenceFingerprint": str(evidence.get("evidenceFingerprint") or ""),
            "checkedAt": str(raw.get("checkedAt") or checked_at),
            "candidateOnly": True,
            "firstPartyVerificationRequired": True,
            "autoCreateAuthorized": False,
            "publicationAuthorized": False,
        }
        items.append(item)

    priority = {
        "first_party_existing_game_reward_change_candidate": 0,
        "moppy_shell_reward_change_candidate": 1,
        "reward_change_candidate": 2,
        "first_party_existing_game_new_offer_candidate": 3,
        "first_party_existing_game_reward_verified": 4,
    }
    items.sort(key=lambda item: (
        priority.get(item["reason"], 99),
        item["game"],
        item["source"],
        item["offerIdentity"],
    ))
    return {
        "phase": "DIRECT_EXISTING_GAME_CANDIDATE_QUEUE_V1",
        "checkedAt": checked_at,
        "candidateOnly": True,
        "firstPartyVerificationRequired": True,
        "autoCreateAuthorized": False,
        "publicationAuthorized": False,
        "count": len(items),
        "rewardChangeCount": sum(
            1 for item in items
            if item["reason"] in {
                "reward_change_candidate",
                "moppy_shell_reward_change_candidate",
                "first_party_existing_game_reward_change_candidate",
            }
        ),
        "newOfferCount": sum(
            1 for item in items
            if item["reason"] == "first_party_existing_game_new_offer_candidate"
        ),
        "verifiedSameRewardCount": sum(
            1 for item in items
            if item["reason"] == "first_party_existing_game_reward_verified"
        ),
        "items": items,
    }


def main(after_scan=None):
    try:
        approvals = load_refresh_approvals()
    except (OSError, ValueError, TypeError):
        print("ERROR: approval registry is unreadable or invalid; no refresh performed", file=sys.stderr)
        return 2
    policy = load_json(POLICY)
    targets = load_json(TARGETS).get("games") or []
    source_cfg = load_json(SOURCES)
    sources = {str(x.get("id") or ""): x for x in (source_cfg.get("sources") or [])}
    offerwall_domains = [
        str(x).lower().strip() for x in (source_cfg.get("offerwall_domains_discovered") or [])
        if str(x).strip()
    ]
    offerwall_presence_cfg = source_cfg.get("offerwall_presence_detection") or {}
    coverage_cfg = source_cfg.get("coverage_discovery") or {}
    policy_coverage_cfg = policy.get("coverageDiscovery") or {}
    coverage_enabled = (
        isinstance(coverage_cfg, dict)
        and coverage_cfg.get("enabled") is True
        and coverage_cfg.get("candidate_only") is True
        and coverage_cfg.get("never_publish") is True
        and isinstance(policy_coverage_cfg, dict)
        and policy_coverage_cfg.get("enabled") is True
        and policy_coverage_cfg.get("mode") == "candidate-only"
        and policy_coverage_cfg.get("requireFirstPartyVerificationBeforePublication") is True
        and policy_coverage_cfg.get("publishFromDiscovery") is False
    )
    coverage_sources = [
        x for x in (coverage_cfg.get("sources") or [])
        if isinstance(x, dict) and str(x.get("id") or "").strip()
    ]
    first_party_coverage_sources = [
        x for x in sources.values()
        if isinstance(x, dict)
        and x.get("discovery_only") is True
        and x.get("coverage_first_party_listing_enabled") is True
        and str(x.get("id") or "").strip()
    ]
    new_game_discovery_sources = [
        x for x in sources.values()
        if isinstance(x, dict)
        and x.get("new_game_discovery_enabled") is True
        and str(x.get("id") or "").strip()
    ]
    try:
        offerwall_provider_registry_path = SOURCES.with_name("offerwall_providers.json")
        offerwall_provider_registry = load_offerwall_provider_registry(
            offerwall_provider_registry_path
        )
        offerwall_provider_label_registry = load_offerwall_provider_label_registry(
            offerwall_provider_registry_path, offerwall_provider_registry
        )
    except (OSError, ValueError, TypeError):
        # Provider enrichment is review-only metadata. If its registry is
        # malformed, omit enrichment rather than affecting publication logic.
        offerwall_provider_registry = {}
        offerwall_provider_label_registry = {}
    offerwall_presence_enabled = (
        isinstance(offerwall_presence_cfg, dict)
        and offerwall_presence_cfg.get("enabled") is True
        and offerwall_presence_cfg.get("follow_external_links") is False
        and offerwall_presence_cfg.get("persist") == "provider_domain_only"
        and offerwall_presence_cfg.get("require_target_context") is True
    )
    comparison_sources = [
        str(x).strip() for x in (policy.get("comparisonSources") or []) if str(x).strip()
    ]
    if not comparison_sources:
        print("ERROR: comparisonSources is empty", file=sys.stderr)
        return 2
    unknown = [x for x in comparison_sources if x not in sources]
    if unknown:
        print("ERROR: unregistered comparison sources: " + ", ".join(unknown), file=sys.stderr)
        return 2

    unified_daily_sources = [
        str(x).strip() for x in (policy.get("unifiedDailySources") or []) if str(x).strip()
    ]
    unified_sources_declared = "unifiedDailySources" in policy
    if unified_sources_declared and not unified_daily_sources:
        print("ERROR: unifiedDailySources is empty", file=sys.stderr)
        return 2
    if not unified_sources_declared:
        unified_daily_sources = list(comparison_sources)
    unknown_unified = [x for x in unified_daily_sources if x not in sources]
    if unknown_unified:
        print("ERROR: unregistered unified daily sources: " + ", ".join(unknown_unified), file=sys.stderr)
        return 2
    invalid_unified = [] if not unified_sources_declared else [
        x for x in unified_daily_sources
        if sources[x].get("new_game_discovery_enabled") is not True
    ]
    if invalid_unified:
        print("ERROR: unified source is not enabled for the shared discovery crawl: "
              + ", ".join(invalid_unified), file=sys.stderr)
        return 2

    original_published = PUBLISHED.read_bytes() if PUBLISHED.exists() else None
    previous_new_game_history = load_new_game_history(NEW_GAME_HISTORY)
    rows = read_published()
    row_by_identity = {
        (
            str(r.get("game") or ""),
            str(r.get("site") or ""),
            offer_identity_key(r.get("url"), str(r.get("site") or "")),
        ): r
        for r in rows
        if r.get("url") and offer_identity_key(r.get("url"), str(r.get("site") or ""))
    }
    changed = 0  # kept for status compatibility; scheduled mode never changes reward values
    review = []
    coverage_candidate_queue = []
    coverage_candidate_seen = set()
    new_game_candidate_queue = []
    new_game_candidate_seen = set()
    results = []
    checked_at = now_iso()
    refreshed = set()
    publication_changed = False
    fetch_cache = {}
    listing_session_openers = {}
    listing_session_bootstrap_requests = 0

    def fetch_once(url, source):
        nonlocal listing_session_bootstrap_requests
        key = (source.get("id"), exact_url_key(url))
        if key not in fetch_cache:
            try:
                if listing_session_required(url, source):
                    source_id = str(source.get("id") or "")
                    bootstrap = str(source.get("listing_session_bootstrap_url") or "").strip()
                    opener = listing_session_openers.get(source_id)
                    if opener is None:
                        opener = build_opener(
                            HTTPCookieProcessor(CookieJar()),
                            FirstPartyRedirectHandler(source),
                        )
                        # Establish the same anonymous first-party session that
                        # the category page uses before its jQuery AJAX request.
                        fetch_first_party(bootstrap, source, opener=opener)
                        listing_session_openers[source_id] = opener
                        listing_session_bootstrap_requests += 1
                    fetch_cache[key] = (
                        fetch_first_party(
                            url,
                            source,
                            opener=opener,
                            extra_headers={
                                "Referer": bootstrap,
                                "X-Requested-With": "XMLHttpRequest",
                                "Accept": "text/html, */*; q=0.01",
                            },
                        ),
                        None,
                    )
                else:
                    fetch_cache[key] = (fetch_first_party(url, source), None)
            except Exception as error:
                if isinstance(error, HTTPError):
                    # Cache the failure, not an open response. No error body is
                    # needed and no retry is authorized by its classification.
                    try:
                        error.close()
                    except OSError:
                        pass  # Preserve/cache the original HTTP failure.
                fetch_cache[key] = (None, error)
        result, error = fetch_cache[key]
        if error is not None:
            raise error
        return result

    listing_snapshots = {}
    listing_snapshot_reuses = 0

    def get_listing_snapshot(url, source, consumer):
        """Fetch one listing URL once and reuse the same snapshot across consumers."""
        nonlocal listing_snapshot_reuses
        key = (str(source.get("id") or ""), exact_url_key(url))
        if key in listing_snapshots:
            listing_snapshot_reuses += 1
            listing_snapshots[key]["consumers"].add(str(consumer or "unknown"))
            result = listing_snapshots[key]["result"]
            error = listing_snapshots[key]["error"]
            if error is not None:
                raise error
            return result

        try:
            result = fetch_once(url, source)
            error = None
        except Exception as exc:
            result = None
            error = exc
        listing_snapshots[key] = {
            "result": result,
            "error": error,
            "consumers": {str(consumer or "unknown")},
        }
        if error is not None:
            raise error
        return result

    def cached_listing_urls_for_source(source, consumer=None):
        source_id = str(source.get("id") or "")
        return [
            url for (sid, url), snapshot in listing_snapshots.items()
            if sid == source_id
            and snapshot.get("result") is not None
            and (
                consumer is None
                or str(consumer) in snapshot.get("consumers", set())
            )
        ]

    new_game_discovery_summary = {
        "sources": 0, "listingPages": 0, "fetchErrors": 0, "candidateCount": 0,
        "completeSources": 0, "incompleteSources": 0, "sourceResults": [],
    }
    for discovery_source in new_game_discovery_sources[:12]:
        new_game_discovery_summary["sources"] += 1
        source_error_start = new_game_discovery_summary["fetchErrors"]
        source_candidate_start = new_game_discovery_summary["candidateCount"]
        listing_limit = max(
            0, min(
                int(discovery_source.get("new_game_discovery_listing_limit")
                    or discovery_source.get("direct_listing_limit") or 0),
                100,
            )
        )
        explicit_listing_urls = [
            str(x).strip() for x in (discovery_source.get("direct_listing_urls") or [])
            if str(x).strip()
        ][:listing_limit]
        page_template = discovery_source.get("new_game_discovery_page_url_template")
        page_cap = max(1, min(int(discovery_source.get("new_game_discovery_max_pages") or 60), 100))
        use_pagination = isinstance(page_template, str) and "{page}" in page_template
        listing_urls = explicit_listing_urls
        if use_pagination:
            listing_urls = [
                paginated_listing_url(discovery_source, page)
                for page in range(1, page_cap + 1)
            ]
            listing_urls = [url for url in listing_urls if url]

        per_source_limit = max(
            1, min(int(discovery_source.get("new_game_discovery_candidate_limit") or 500), 2000)
        )
        remaining = per_source_limit
        seen_page_signatures = set()
        source_complete = not use_pagination
        pages_attempted = 0
        content_guard_failed = False
        min_first_page_identities = max(
            0, min(
                int(discovery_source.get("new_game_discovery_min_detail_identities_first_page") or 0),
                100,
            )
        )

        for listing_url in listing_urls:
            if remaining <= 0:
                break
            pages_attempted += 1
            new_game_discovery_summary["listingPages"] += 1
            if not source_host_allowed(listing_url, discovery_source):
                new_game_discovery_summary["fetchErrors"] += 1
                continue
            try:
                raw, final_url = get_listing_snapshot(listing_url, discovery_source, "new_game_discovery")
                signature = listing_detail_identity_signature(
                    raw, final_url, discovery_source, limit=5000
                )
                if use_pagination:
                    if pages_attempted == 1 and len(signature) < min_first_page_identities:
                        content_guard_failed = True
                        new_game_discovery_summary["fetchErrors"] += 1
                        break
                    if not signature:
                        source_complete = True
                        break
                    if signature in seen_page_signatures:
                        source_complete = True
                        break
                    seen_page_signatures.add(signature)
                runtime_source = dict(discovery_source)
                runtime_source["full_catalog_discovery_enabled"] = (
                    discovery_source.get("full_catalog_discovery_enabled") is True
                    or (use_pagination and source_complete)
                )
                candidates = discover_new_game_listing_candidates(
                    raw, final_url, runtime_source, targets, limit=remaining
                )
            except Exception:
                new_game_discovery_summary["fetchErrors"] += 1
                continue

            for candidate in candidates:
                key = (
                    candidate.get("source"),
                    candidate.get("offerIdentity"),
                )
                if key in new_game_candidate_seen:
                    continue
                new_game_candidate_seen.add(key)
                candidate["checkedAt"] = checked_at
                candidate.update(classify_new_game_candidate(candidate))
                new_game_candidate_queue.append(candidate)
                new_game_discovery_summary["candidateCount"] += 1
                remaining -= 1
                if remaining <= 0:
                    break

        candidate_limit_reached = remaining <= 0
        source_errors = new_game_discovery_summary["fetchErrors"] - source_error_start
        source_incomplete = (
            source_errors > 0
            or content_guard_failed
            or candidate_limit_reached
            or (use_pagination and not source_complete)
        )
        if source_incomplete:
            new_game_discovery_summary["incompleteSources"] += 1
        else:
            new_game_discovery_summary["completeSources"] += 1

        source_candidates = new_game_discovery_summary["candidateCount"] - source_candidate_start
        catalog_complete = (
            source_errors == 0
            and not candidate_limit_reached
            and not content_guard_failed
            and (
                discovery_source.get("full_catalog_discovery_enabled") is True
                or (use_pagination and source_complete)
            )
        )
        scan_complete = (
            source_errors == 0
            and not content_guard_failed
            and not candidate_limit_reached
            and (not use_pagination or source_complete)
        )
        new_game_discovery_summary["sourceResults"].append({
            "source": str(discovery_source.get("id") or ""),
            "sourceLabel": str(discovery_source.get("name") or discovery_source.get("id") or ""),
            "scope": str(
                discovery_source.get("new_game_discovery_scope")
                or discovery_source.get("coverage_scope")
                or "unspecified"
            ),
            "rankingRequired": source_participates_in_new_game_ranking(discovery_source),
            "listingPagesAttempted": pages_attempted,
            "fetchErrors": source_errors,
            "candidateCount": source_candidates,
            "scanComplete": scan_complete,
            "catalogComplete": catalog_complete,
            "candidateLimitReached": candidate_limit_reached,
            "contentGuardFailed": content_guard_failed,
        })

    for target in targets:
        game = str(target.get("game") or "").strip()
        game_policy = (policy.get("games") or {}).get(game) or {}
        if game_policy.get("enabled") is not True:
            continue
        aliases = [game] + [str(x) for x in (target.get("aliases") or []) if str(x).strip()]
        supplemental = [
            str(x).strip() for x in (game_policy.get("supplementalSources") or []) if str(x).strip()
        ]
        published_sources = [str(r.get("site") or "") for r in rows
                             if r.get("game") == game and r.get("site")]
        requested = list(dict.fromkeys(unified_daily_sources + comparison_sources + supplemental + published_sources))
        game_result = {"game": game, "sources": [], "standardConfirmed": 0}

        for source_id in requested:
            if source_id not in sources:
                review.append({
                    "game": game, "source": source_id, "reason": "unregistered_source",
                    "checkedAt": checked_at
                })
                continue
            source = sources[source_id]
            is_standard = source_id in unified_daily_sources
            current_rows = [
                r for r in rows
                if str(r.get("game") or "") == game and str(r.get("site") or "") == source_id
            ]
            reuse_unified_listing = (
                unified_sources_declared
                and source_id in unified_daily_sources
                and source.get("new_game_discovery_enabled") is True
            )
            if (source.get("scheduled_fetch_enabled", True) is not True
                    and not reuse_unified_listing):
                review.append({
                    "game": game,
                    "source": source_id,
                    "reason": "scheduled_source_fetch_disabled",
                    "existingRows": len(current_rows),
                    "checkedAt": checked_at,
                })
                game_result["sources"].append({
                    "source": source_id,
                    "standard": is_standard,
                    "knownOrDiscoveredUrls": 0,
                    "confirmedOffers": 0,
                    "updatedRows": 0,
                    "reviewRequired": 1,
                    "state": "review_required",
                })
                continue
            urls = []
            known_detail_fetch_enabled = source.get("scheduled_known_detail_fetch_enabled", True) is True
            if known_detail_fetch_enabled:
                for u in ((target.get("known_urls_by_source") or {}).get(source_id) or []):
                    if source_host_allowed(u, source):
                        urls.append(u)
                for r in current_rows:
                    u = str(r.get("url") or "")
                    if u and source_host_allowed(u, source):
                        urls.append(u)

            listing_errors = []
            discovered = []
            offerwall_presence = []
            listing_limit = max(0, min(2, int(source.get("direct_listing_limit", 2))))
            detail_limit = max(0, min(6, int(source.get("direct_detail_limit", 6))))
            if reuse_unified_listing:
                detail_limit = max(
                    detail_limit,
                    max(0, min(6, int(source.get("coverage_detail_review_limit_per_game") or 0))),
                )
            cached_discovery_listing_urls = cached_listing_urls_for_source(
                source, consumer="new_game_discovery"
            )
            existing_listing_urls = (
                cached_discovery_listing_urls
                if cached_discovery_listing_urls
                else target_listing_urls(source, aliases)[:listing_limit]
            )
            for listing_url in existing_listing_urls:
                try:
                    raw, final_url = get_listing_snapshot(listing_url, source, "existing_game_refresh")
                    if target_present(visible_text(raw), aliases):
                        discovered.extend(discover_detail_links(raw, final_url, source, aliases, limit=6))
                        if offerwall_presence_enabled:
                            offerwall_presence.extend(
                                discover_offerwall_presence(raw, final_url, aliases, offerwall_domains, limit=6)
                            )
                except Exception as e:
                    listing_errors.append({"url": listing_url, "error": summarize_fetch_error(e)})
            urls.extend(discovered)
            offerwall_presence = list(dict.fromkeys(offerwall_presence))
            offerwall_candidates = offerwall_provider_candidates(
                offerwall_presence, offerwall_provider_registry
            )
            deduped_urls = []
            seen_identities = set()
            for candidate_url in urls:
                exact = exact_url_key(candidate_url)
                identity = offer_identity_key(exact, source_id)
                if not exact or not identity or identity in seen_identities:
                    continue
                seen_identities.add(identity)
                deduped_urls.append(exact)
            # The discovery budget must not truncate already published offers.
            published_identities = {
                offer_identity_key(r.get("url"), source_id) for r in current_rows
            } if known_detail_fetch_enabled else set()
            published_urls = [u for u in deduped_urls
                              if offer_identity_key(u, source_id) in published_identities]
            discovery_urls = [u for u in deduped_urls
                              if offer_identity_key(u, source_id) not in published_identities]
            if unified_sources_declared and source_id in unified_daily_sources:
                for observed_url in discovery_urls:
                    review.append({
                        "game": game,
                        "source": source_id,
                        "url": observed_url,
                        "reason": "first_party_existing_game_listing_offer_observed",
                        "candidateOnly": True,
                        "publicationAuthorized": False,
                        "checkedAt": checked_at,
                    })
            discovery_budget = max(0, detail_limit - len(published_urls))
            urls = published_urls + discovery_urls[:discovery_budget]

            source_result = {
                "source": source_id,
                "standard": is_standard,
                "knownOrDiscoveredUrls": len(urls),
                "offerwallPresenceDomains": len(offerwall_presence),
                "offerwallReviewedProviders": len(offerwall_candidates),
                "confirmedOffers": 0,
                "updatedRows": 0,
                "reviewRequired": 0,
            }
            if len(discovery_urls) > discovery_budget:
                review.append({
                    "game": game, "source": source_id, "reason": "detail_limit_reached",
                    "deferredCount": len(discovery_urls) - discovery_budget,
                    "checkedAt": checked_at,
                })
                source_result["reviewRequired"] += 1

            if not urls:
                if offerwall_presence:
                    review.append({
                        "game": game,
                        "source": source_id,
                        "reason": "offerwall_presence_candidate",
                        "providerDomains": offerwall_presence,
                        "providerCandidates": offerwall_candidates,
                        "listingErrors": [item["error"] for item in listing_errors],
                        "checkedAt": checked_at,
                    })
                else:
                    review.append({
                        "game": game, "source": source_id, "reason": "discovery_required",
                        "listingErrors": [item["error"] for item in listing_errors],
                        "knownDetailFetchEnabled": known_detail_fetch_enabled,
                        "checkedAt": checked_at
                    })
                source_result["reviewRequired"] += 1
                source_result["state"] = "review_required"
                game_result["sources"].append(source_result)
                continue

            if offerwall_presence:
                review.append({
                    "game": game,
                    "source": source_id,
                    "reason": "offerwall_presence_candidate",
                    "providerDomains": offerwall_presence,
                    "listingErrors": [item["error"] for item in listing_errors],
                    "checkedAt": checked_at,
                })
                source_result["reviewRequired"] += 1

            # Existing detail URLs do not imply the discovery listing worked.
            # Preserve each failure while still inspecting known offers.
            for listing_error in listing_errors:
                review.append({
                    "game": game, "source": source_id, "url": listing_error["url"],
                    "reason": "listing_fetch_failed", "error": listing_error["error"],
                    "checkedAt": checked_at,
                })
                source_result["reviewRequired"] += 1

            for url in urls:
                try:
                    detail = inspect_detail(
                        url, source, aliases, fetcher=fetch_once,
                        provider_label_registry=offerwall_provider_label_registry,
                    )
                except Exception as e:
                    review.append({
                        "game": game, "source": source_id, "url": url,
                        "reason": "fetch_failed", "error": summarize_fetch_error(e), "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1
                    continue

                evidence = detail.get("sourceEvidence")
                if evidence is not None:
                    if evidence.get("state") == "parsed" and evidence.get("downstreamTermsRequired") is True:
                        provider_candidates = offerwall_provider_candidates_from_text(
                            evidence.get("termsText", ""), offerwall_provider_label_registry
                        )
                        if provider_candidates:
                            evidence = dict(evidence)
                            evidence["downstreamProviderCandidates"] = provider_candidates
                    existing = row_by_identity.get((game, source_id, offer_identity_key(url, source_id)))
                    item = {"game": game, "source": source_id, "url": detail["url"],
                            "reason": "structured_offer_review_required" if evidence["state"] == "parsed"
                            else evidence.get("reason", "source_structure_review_required"),
                            "sourceEvidence": evidence, "checkedAt": checked_at}
                    if (
                        existing is None
                        and source_id == "coincome"
                        and evidence.get("state") == "parsed"
                        and evidence.get("parserVersion") == "coincome-detail-review-v2"
                        and type(evidence.get("displayedRewardYen")) is int
                        and evidence.get("displayedRewardYen") > 0
                    ):
                        item.update({
                            "reason": "first_party_existing_game_new_offer_candidate",
                            "detectedReward": evidence["displayedRewardYen"],
                            "platformHint": evidence.get("platform") or "",
                            "candidateOnly": True,
                            "firstPartyVerificationRequired": True,
                            "autoCreateAuthorized": False,
                            "publicationAuthorized": False,
                        })
                    if existing is not None:
                        item["storedPlatform"] = existing.get("platform") or ""
                        item["storedReward"] = existing.get("reward") or ""
                        if evidence["state"] == "parsed":
                            item["platformMatches"] = evidence["platform"] == existing.get("platform")
                            item["requiredChecks"] = ["reward_unit_conversion", "complete_terms_vs_published_row"]
                            if source_id == "moppy":
                                displayed = evidence.get("displayedRewardPoints")
                                try:
                                    stored = int(str(existing.get("reward") or "").replace(",", ""))
                                except (TypeError, ValueError):
                                    stored = None
                                item["shellDisplayedReward"] = displayed
                                item["shellRewardMatchesStored"] = (
                                    type(displayed) is int and stored is not None and displayed == stored
                                )
                                if type(displayed) is int and stored is not None and displayed != stored:
                                    item["reason"] = "moppy_shell_reward_change_candidate"
                                    item["detectedReward"] = displayed
                                    item["candidateOnly"] = True
                                    item["publicationAuthorized"] = False
                                    item["requiredChecks"] = [
                                        "point_get_destination_reward",
                                        "complete_terms_vs_published_row",
                                    ]
                            if source_id == "warau":
                                reason = approved_refresh_reason(existing, evidence,
                                    approvals.get(existing.get("offerKey")), checked_at)
                            elif source_id == "moppy":
                                # Moppy's audited parser binds the stable offer identity and
                                # current reward to dedicated first-party DOM. Reward-only refresh
                                # is safe; terms/platform summaries remain untouched.
                                if evidence.get("parserVersion") not in {
                                    "moppy-detail-review-v2", "moppy-detail-review-v3"
                                }:
                                    reason = "source_evidence_not_supported"
                                elif type(evidence.get("displayedRewardPoints")) is not int:
                                    reason = "missing_current_reward"
                                elif existing.get("verified") != "true":
                                    reason = "published_row_not_verified"
                                else:
                                    existing["reward"] = str(evidence["displayedRewardPoints"])
                                    item["candidateOnly"] = False
                                    item["publicationAuthorized"] = True
                                    reason = None
                            else:
                                reason = "source_refresh_not_enabled"
                            identity_rows = [r for r in current_rows
                                if offer_identity_key(r.get("url"), source_id) == offer_identity_key(url, source_id)]
                            if len(identity_rows) != 1 or sum(r.get("offerKey") == existing.get("offerKey") for r in rows) != 1:
                                reason = "ambiguous_published_identity"
                            if reason is None:
                                check_date = datetime.fromisoformat(checked_at).astimezone(
                                    timezone(timedelta(hours=9))).date().isoformat()
                                if existing.get("updatedAt") != check_date:
                                    existing["updatedAt"] = check_date
                                    publication_changed = True
                                refreshed.add(existing["offerKey"])
                                source_result["confirmedOffers"] += 1
                                source_result["updatedRows"] += 1
                                continue
                            item["approvalHoldReason"] = reason
                    review.append(item)
                    source_result["reviewRequired"] += 1
                    continue

                if not detail["targetPresent"]:
                    review.append({
                        "game": game, "source": source_id, "url": detail["url"],
                        "reason": "target_not_confirmed", "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1
                    continue

                key = (game, source_id, offer_identity_key(url, source_id))
                existing = row_by_identity.get(key)
                if source.get("generic_reward_detection_enabled", True) is not True:
                    item = {
                        "game": game,
                        "source": source_id,
                        "url": detail["url"],
                        "reason": "source_specific_reward_parser_required",
                        "platformHint": detail.get("platform") or "",
                        "checkedAt": checked_at,
                    }
                    if existing is not None:
                        item["storedReward"] = existing.get("reward") or ""
                        item["storedPlatform"] = existing.get("platform") or ""
                    review.append(item)
                    source_result["reviewRequired"] += 1
                    continue

                if existing is None:
                    review.append({
                        "game": game, "source": source_id, "url": detail["url"],
                        "reason": "unpublished_offer_found",
                        "detectedStrongRewards": detail.get("strongCandidates") or [],
                        "detectedWeakRewards": detail.get("weakCandidates") or [],
                        "platformHint": detail["platform"],
                        "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1
                    continue

                try:
                    old_reward = int(float(existing.get("reward") or 0))
                except Exception:
                    old_reward = 0
                detected, reward_method, strong, weak, generic = choose_existing_reward(
                    detail.get("_text") or "", old_reward
                )

                if detected is not None and detected == old_reward:
                    # A page-wide numeric match is discovery evidence only.
                    # It does not bind the amount/unit, OS and complete terms to
                    # this offer. Keep all published fields unchanged until a
                    # source-specific verifier can establish that binding.
                    review.append({
                        "game": game, "source": source_id, "url": detail["url"],
                        "reason": "offer_terms_review_required",
                        "storedReward": old_reward,
                        "detectedReward": detected,
                        "rewardMethod": reward_method,
                        "storedPlatform": existing.get("platform") or "",
                        "platformHint": detail.get("platform") or "",
                        "requiredChecks": [
                            "offer_identity", "reward_unit", "platform",
                            "achievement_conditions", "deadline", "availability",
                        ],
                        "checkedAt": checked_at,
                    })
                    source_result["reviewRequired"] += 1
                elif detected is not None and detected != old_reward:
                    review.append({
                        "game": game, "source": source_id, "url": detail["url"],
                        "reason": "reward_change_candidate",
                        "storedReward": old_reward,
                        "detectedReward": detected,
                        "rewardMethod": reward_method,
                        "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1
                else:
                    review.append({
                        "game": game, "source": source_id, "url": detail["url"],
                        "reason": "reward_review_required",
                        "rewardMethod": reward_method,
                        "storedReward": old_reward,
                        "strongCandidates": strong,
                        "weakCandidates": weak,
                        "genericCandidates": generic[-12:],
                        "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1

            if source_result["updatedRows"] > 0:
                source_result["state"] = "confirmed"
                if is_standard:
                    game_result["standardConfirmed"] += 1
            elif source_result["reviewRequired"] > 0:
                source_result["state"] = "review_required"
            else:
                source_result["state"] = "not_confirmed"
            game_result["sources"].append(source_result)

        coverage_summary = {
            "enabled": coverage_enabled,
            "candidateCount": 0,
            "gapCount": 0,
            "coveredCount": 0,
            "fetchErrors": 0,
            "detailReviewCount": 0,
            "verifiedRewardCandidateCount": 0,
        }
        if coverage_enabled:
            for discovery_source in coverage_sources[:3]:
                query_url = coverage_query_url(discovery_source, aliases)
                if not query_url:
                    coverage_summary["fetchErrors"] += 1
                    review.append({
                        "game": game,
                        "source": str(discovery_source.get("id") or ""),
                        "reason": "coverage_discovery_config_invalid",
                        "checkedAt": checked_at,
                    })
                    continue
                try:
                    raw, final_url = fetch_once(query_url, discovery_source)
                    max_candidates = int(discovery_source.get("max_candidates_per_game") or 24)
                    candidates = discover_coverage_candidates(
                        raw, aliases, discovery_source, limit=max_candidates
                    )
                except Exception as error:
                    coverage_summary["fetchErrors"] += 1
                    review.append({
                        "game": game,
                        "source": str(discovery_source.get("id") or ""),
                        "url": query_url,
                        "reason": "coverage_discovery_fetch_failed",
                        "error": summarize_fetch_error(error),
                        "checkedAt": checked_at,
                    })
                    continue

                coverage_summary["candidateCount"] += len(candidates)
                for candidate in candidates:
                    if coverage_candidate_is_covered(candidate, rows, game):
                        coverage_summary["coveredCount"] += 1
                        continue
                    coverage_summary["gapCount"] += 1
                    discovery_source_id = str(discovery_source.get("id") or "")
                    queue_item = coverage_candidate_queue_item(
                        game, candidate, discovery_source_id, final_url, checked_at, sources
                    )
                    queue_key = coverage_candidate_key(game, candidate, discovery_source_id)
                    if queue_key not in coverage_candidate_seen:
                        coverage_candidate_seen.add(queue_key)
                        coverage_candidate_queue.append(queue_item)
                    review.append({
                        **queue_item,
                        "reason": "external_coverage_gap_candidate",
                    })

            for discovery_source in first_party_coverage_sources[:6]:
                detail_review_enabled = discovery_source.get("coverage_detail_review_enabled") is True
                detail_review_remaining = max(
                    0, min(
                        int(discovery_source.get("coverage_detail_review_limit_per_game") or 0),
                        8,
                    )
                )
                configured_listing_urls = [
                    str(x).strip() for x in (discovery_source.get("direct_listing_urls") or [])
                    if str(x).strip()
                ]
                paginated_discovery = (
                    isinstance(discovery_source.get("new_game_discovery_page_url_template"), str)
                    and "{page}" in discovery_source.get("new_game_discovery_page_url_template", "")
                )
                if (
                    discovery_source.get("full_catalog_discovery_enabled") is True
                    or paginated_discovery
                ):
                    listing_urls = cached_listing_urls_for_source(
                        discovery_source, consumer="new_game_discovery"
                    )
                    if not listing_urls and discovery_source.get("full_catalog_discovery_enabled") is True:
                        listing_urls = configured_listing_urls[
                            :max(0, min(100, int(discovery_source.get("direct_listing_limit", 1))))
                        ]
                    elif not listing_urls:
                        listing_urls = configured_listing_urls[
                            :max(0, min(2, int(discovery_source.get("direct_listing_limit", 1))))
                        ]
                else:
                    listing_urls = configured_listing_urls[
                        :max(0, min(2, int(discovery_source.get("direct_listing_limit", 1))))
                    ]
                for listing_url in listing_urls:
                    if not source_host_allowed(listing_url, discovery_source):
                        coverage_summary["fetchErrors"] += 1
                        review.append({
                            "game": game,
                            "source": str(discovery_source.get("id") or ""),
                            "url": listing_url,
                            "reason": "first_party_coverage_config_invalid",
                            "checkedAt": checked_at,
                        })
                        continue
                    try:
                        raw, final_url = get_listing_snapshot(listing_url, discovery_source, "known_game_coverage")
                        candidates = discover_first_party_listing_candidates(
                            raw, final_url, discovery_source, aliases,
                            limit=max(1, min(8, int(discovery_source.get("coverage_candidate_limit") or 4))),
                        )
                    except Exception as error:
                        coverage_summary["fetchErrors"] += 1
                        review.append({
                            "game": game,
                            "source": str(discovery_source.get("id") or ""),
                            "url": listing_url,
                            "reason": "first_party_coverage_fetch_failed",
                            "error": summarize_fetch_error(error),
                            "checkedAt": checked_at,
                        })
                        continue

                    coverage_summary["candidateCount"] += len(candidates)
                    for candidate in candidates:
                        if detail_review_enabled and detail_review_remaining > 0:
                            candidate_url = str(candidate.get("firstPartyCandidateUrl") or "").strip()
                            if candidate_url and source_host_allowed(candidate_url, discovery_source):
                                detail_review_remaining -= 1
                                try:
                                    detail = inspect_detail(
                                        candidate_url,
                                        discovery_source,
                                        aliases,
                                        fetcher=fetch_once,
                                        provider_label_registry=offerwall_provider_label_registry,
                                    )
                                    evidence = detail.get("sourceEvidence")
                                    coverage_summary["detailReviewCount"] += 1
                                    if (
                                        isinstance(evidence, dict)
                                        and evidence.get("state") == "parsed"
                                        and type(evidence.get("verifiedCurrentRewardYen")) is int
                                    ):
                                        coverage_summary["verifiedRewardCandidateCount"] += 1
                                        source_id = str(discovery_source.get("id") or "")
                                        detected_reward = evidence["verifiedCurrentRewardYen"]
                                        identity = offer_identity_key(candidate_url, source_id)
                                        existing = row_by_identity.get((game, source_id, identity))
                                        reason = "first_party_existing_game_new_offer_candidate"
                                        stored_reward = None
                                        reward_matches_stored = None
                                        if existing is not None:
                                            try:
                                                stored_reward = int(str(existing.get("reward") or "").replace(",", ""))
                                            except (TypeError, ValueError):
                                                stored_reward = None
                                            if stored_reward is not None:
                                                reward_matches_stored = detected_reward == stored_reward
                                                reason = (
                                                    "first_party_existing_game_reward_verified"
                                                    if reward_matches_stored
                                                    else "first_party_existing_game_reward_change_candidate"
                                                )
                                        item = {
                                            "game": game,
                                            "source": source_id,
                                            "url": detail.get("url") or candidate_url,
                                            "reason": reason,
                                            "detectedReward": detected_reward,
                                            "platformHint": evidence.get("platform") or "",
                                            "sourceEvidence": evidence,
                                            "candidateOnly": True,
                                            "firstPartyVerificationRequired": True,
                                            "autoCreateAuthorized": False,
                                            "publicationAuthorized": False,
                                            "checkedAt": checked_at,
                                        }
                                        if stored_reward is not None:
                                            item["storedReward"] = stored_reward
                                            item["rewardMatchesStored"] = reward_matches_stored
                                        review.append(item)
                                    else:
                                        review.append({
                                            "game": game,
                                            "source": str(discovery_source.get("id") or ""),
                                            "url": detail.get("url") or candidate_url,
                                            "reason": "first_party_existing_game_detail_review_required",
                                            "sourceEvidence": evidence or {},
                                            "candidateOnly": True,
                                            "publicationAuthorized": False,
                                            "checkedAt": checked_at,
                                        })
                                except Exception as error:
                                    coverage_summary["fetchErrors"] += 1
                                    review.append({
                                        "game": game,
                                        "source": str(discovery_source.get("id") or ""),
                                        "url": candidate_url,
                                        "reason": "first_party_existing_game_detail_fetch_failed",
                                        "error": summarize_fetch_error(error),
                                        "candidateOnly": True,
                                        "publicationAuthorized": False,
                                        "checkedAt": checked_at,
                                    })

                        if coverage_candidate_is_covered(candidate, rows, game):
                            coverage_summary["coveredCount"] += 1
                            continue
                        coverage_summary["gapCount"] += 1
                        discovery_source_id = str(discovery_source.get("id") or "")
                        queue_item = coverage_candidate_queue_item(
                            game, candidate, discovery_source_id, final_url, checked_at, sources
                        )
                        queue_key = coverage_candidate_key(game, candidate, discovery_source_id)
                        if queue_key not in coverage_candidate_seen:
                            coverage_candidate_seen.add(queue_key)
                            coverage_candidate_queue.append(queue_item)
                        review.append({
                            **queue_item,
                            "reason": "first_party_coverage_gap_candidate",
                        })
        game_result["coverageDiscovery"] = coverage_summary

        game_result["standardTotal"] = len(unified_daily_sources)
        game_result["comparisonReady"] = (
            game_result["standardConfirmed"] >= int(policy.get("minimumConfirmedSourcesForComparison") or 2)
        )
        results.append(game_result)

    # Consume the same in-memory snapshots before they are released. The hook
    # is optional, cannot silently fail, and runs before any publication write.
    if after_scan is not None:
        before_hook = [dict(row) for row in rows]
        hook_result = after_scan(items=new_game_candidate_queue, sources=sources, targets=targets,
                   rows=rows, checked_at=checked_at, fetcher=fetch_once,
                   review_items=review, publication_policy=policy.get("structuredPublication", {})) or {}
        publication_changed = publication_changed or before_hook != rows
        changed = sum(old.get("reward") != new.get("reward") for old, new in zip(before_hook, rows))
        confirmed_keys = set(hook_result.get("confirmedOfferKeys", []))
        refreshed.update(confirmed_keys)
        for game_result in results:
            for source_result in game_result["sources"]:
                confirmed = sum(row.get("offerKey") in confirmed_keys for row in rows
                    if row.get("game") == game_result["game"] and row.get("site") == source_result["source"])
                if confirmed:
                    source_result["confirmedOffers"] = max(source_result["confirmedOffers"], confirmed)
                    source_result["updatedRows"] = max(source_result["updatedRows"], confirmed)
                    source_result["state"] = "confirmed"
            game_result["standardConfirmed"] = sum(s.get("standard") is True and s["state"] == "confirmed"
                                                     for s in game_result["sources"])
            game_result["comparisonReady"] = game_result["standardConfirmed"] >= int(policy.get("minimumConfirmedSourcesForComparison") or 2)

    if publication_changed:
        if not PUBLISHED.exists() or PUBLISHED.read_bytes() != original_published:
            print("ERROR: published data changed during refresh; refusing to overwrite", file=sys.stderr)
            return 2
        write_published(rows)

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "phase": "DIRECT_COMPARISON_REFRESH_V1",
        "checkedAt": checked_at,
        "coverageDiscoveryVersion": 2,
        "coverageDiscoveryMode": "candidate-only" if coverage_enabled else "disabled",
        "comparisonSources": comparison_sources,
        "unifiedDailySources": unified_daily_sources,
        "apiCalls": 0,
        "publishedRewardChanges": changed,
        "refreshedRows": len(refreshed),
        "reviewCount": len(review),
        "existingRewardChangeCandidateCount": sum(
            1 for item in review
            if str(item.get("reason") or "") in {
                "reward_change_candidate",
                "moppy_shell_reward_change_candidate",
                "first_party_existing_game_reward_change_candidate",
            }
        ),
        "existingGameNewOfferCandidateCount": sum(
            1 for item in review
            if str(item.get("reason") or "") == "first_party_existing_game_new_offer_candidate"
        ),
        "existingGameVerifiedRewardCount": sum(
            1 for item in review
            if str(item.get("reason") or "") == "first_party_existing_game_reward_verified"
        ),
        "coverageCandidateQueueCount": len(coverage_candidate_queue),
        "newGameCandidateQueueCount": len(new_game_candidate_queue),
        "newGameDiscovery": new_game_discovery_summary,
        "listingSnapshot": {
            "mode": "fetch_once_reuse_many",
            "uniqueListings": len(listing_snapshots),
            "uniqueRequests": len(fetch_cache) + listing_session_bootstrap_requests,
            "sessionBootstrapRequests": listing_session_bootstrap_requests,
            "failedRequests": sum(error is not None for _, error in fetch_cache.values()),
            "reuseCount": listing_snapshot_reuses,
            "consumers": sorted({
                consumer
                for snapshot in listing_snapshots.values()
                for consumer in snapshot.get("consumers", set())
            }),
        },
        "games": results,
        "success": True,
    }
    tmp = STATUS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATUS)

    compatibility_results = []
    for game_result in results:
        ready = bool(game_result.get("comparisonReady"))
        refreshed = sum(
            int(x.get("updatedRows") or 0)
            for x in (game_result.get("sources") or [])
            if x.get("standard") is True
        )
        compatibility_results.append({
            "game": game_result.get("game"),
            "returncode": 0,
            "publishableCount": refreshed,
            "collectionComplete": ready,
            "degradedReasons": [] if ready else ["comparison_sources_below_minimum"],
            "standardConfirmed": game_result.get("standardConfirmed", 0),
            "standardTotal": game_result.get("standardTotal", 0),
        })

    compatibility = {
        "phase": "DIRECT_COMPARISON_REFRESH_V1",
        "startedAt": checked_at,
        "finishedAt": checked_at,
        "enabledGames": [x.get("game") for x in results],
        "results": compatibility_results,
        "success": True,
    }
    tmp_legacy = LEGACY_STATUS.with_suffix(".json.tmp")
    tmp_legacy.write_text(json.dumps(compatibility, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_legacy.replace(LEGACY_STATUS)

    review_payload = {
        "phase": "DIRECT_COMPARISON_REVIEW_V1",
        "checkedAt": checked_at,
        "coverageDiscoveryVersion": 2,
        "items": review,
    }
    tmp2 = REVIEW.with_suffix(".json.tmp")
    tmp2.write_text(json.dumps(review_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp2.replace(REVIEW)

    candidate_path = REVIEW.with_name("comparison_candidate_queue.json")
    candidate_payload = {
        "phase": "DIRECT_COMPARISON_CANDIDATE_QUEUE_V1",
        "checkedAt": checked_at,
        "coverageDiscoveryVersion": 2,
        "candidateOnly": True,
        "firstPartyVerificationRequired": True,
        "publicationAuthorized": False,
        "count": len(coverage_candidate_queue),
        "items": coverage_candidate_queue,
    }
    tmp3 = candidate_path.with_suffix(".json.tmp")
    tmp3.write_text(json.dumps(candidate_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp3.replace(candidate_path)

    new_game_clusters = build_new_game_candidate_clusters(new_game_candidate_queue)
    new_game_review_priority = build_new_game_review_priority(
        new_game_candidate_queue, new_game_clusters
    )
    new_game_history = build_new_game_history(
        new_game_candidate_queue, previous_new_game_history, checked_at
    )
    new_today_keys = {
        key for key, item in new_game_history["items"].items()
        if item.get("active") is True and item.get("isNewToday") is True
    }
    for item in new_game_candidate_queue:
        item["firstSeen"] = (
            new_game_history["items"].get(new_game_history_key(item), {}).get("firstSeen")
        )
        item["isNewToday"] = new_game_history_key(item) in new_today_keys

    new_game_payload = {
        "phase": "DIRECT_NEW_GAME_CANDIDATE_QUEUE_V1",
        "checkedAt": checked_at,
        "candidateOnly": True,
        "firstPartyVerificationRequired": True,
        "autoCreateAuthorized": False,
        "publicationAuthorized": False,
        "count": len(new_game_candidate_queue),
        "newTodayCount": len(new_today_keys),
        "likelyGameCount": sum(1 for x in new_game_candidate_queue if x.get("classification") == "likely_game"),
        "likelyNonGameCount": sum(1 for x in new_game_candidate_queue if x.get("classification") == "likely_non_game"),
        "reviewClassificationCount": sum(1 for x in new_game_candidate_queue if x.get("classification") == "review"),
        "clusterCount": len(new_game_clusters),
        "clusters": new_game_clusters,
        "reviewPriority": new_game_review_priority,
        "items": new_game_candidate_queue,
    }
    tmp4 = NEW_GAME_QUEUE.with_suffix(".json.tmp")
    tmp4.write_text(json.dumps(new_game_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp4.replace(NEW_GAME_QUEUE)

    tmp5 = NEW_GAME_HISTORY.with_suffix(".json.tmp")
    tmp5.write_text(json.dumps(new_game_history, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp5.replace(NEW_GAME_HISTORY)

    existing_game_payload = build_existing_game_candidate_queue(review, checked_at)
    tmp6 = EXISTING_GAME_QUEUE.with_suffix(".json.tmp")
    tmp6.write_text(
        json.dumps(existing_game_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp6.replace(EXISTING_GAME_QUEUE)

    print("Direct comparison refresh complete")
    print("API calls: 0")
    print("Reward changes:", changed)
    print("Review items:", len(review))
    for g in results:
        print(f"{g['game']}: standard confirmed {g['standardConfirmed']}/{g['standardTotal']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
