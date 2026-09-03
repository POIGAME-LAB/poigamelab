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
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "refresh_policy.json"
TARGETS = ROOT / "config" / "game_targets.json"
SOURCES = ROOT / "config" / "point_sources.json"
PUBLISHED = ROOT / "data" / "published_offers.csv"
STATUS = ROOT / "data" / "comparison_refresh_status.json"
LEGACY_STATUS = ROOT / "data" / "refresh_status.json"
REVIEW = ROOT / "data" / "comparison_review_queue.json"

FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
]

DETAIL_QUERY_KEYS = {"point_id", "site_id", "itemid", "campaign_id", "campaignid", "id"}

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def today_jst():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def source_host_allowed(url, source):
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    domains = [str(x).lower().strip() for x in (source.get("search_domains") or []) if str(x).strip()]
    return any(host == d or host.endswith("." + d) for d in domains)

class FirstPartyRedirectHandler(HTTPRedirectHandler):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not source_host_allowed(newurl, self.source):
            raise ValueError("redirect left registered first-party domains")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_first_party(url, source, timeout=15, max_bytes=1200000):
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
    req = Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
    })
    opener = build_opener(FirstPartyRedirectHandler(source))
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
    return data.decode(charset or "utf-8", errors="replace"), final_url

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

def discover_detail_links(raw, base_url, source, aliases, limit=8):
    found = []
    seen = set()
    for m in re.finditer(r'(?is)<a\b[^>]*?href\s*=\s*(["\'])(.*?)\1[^>]*>(.*?)</a>', raw or ""):
        href = html.unescape(m.group(2)).strip()
        absolute = urljoin(base_url, href)
        if not source_host_allowed(absolute, source) or not detail_like(absolute, source):
            continue
        start = max(0, m.start() - 650)
        end = min(len(raw), m.end() + 650)
        context = visible_text(raw[start:end])
        label = visible_text(m.group(3))
        if not (target_present(label, aliases) or target_present(context, aliases)):
            continue
        key = absolute.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        found.append(key)
        if len(found) >= limit:
            break
    return found

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

    for key in ("point_id", "site_id", "itemid", "campaign_id", "campaignid", "id"):
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


def inspect_detail(url, source, aliases, fetcher=None):
    raw, final_url = (fetcher or fetch_first_party)(url, source)
    if source.get("id") == "warau":
        evidence = inspect_warau_offer(raw, url, final_url, aliases)
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

def main():
    policy = load_json(POLICY)
    targets = load_json(TARGETS).get("games") or []
    source_cfg = load_json(SOURCES)
    sources = {str(x.get("id") or ""): x for x in (source_cfg.get("sources") or [])}
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
    results = []
    checked_at = now_iso()
    fetch_cache = {}

    def fetch_once(url, source):
        key = (source.get("id"), exact_url_key(url))
        if key not in fetch_cache:
            try:
                fetch_cache[key] = (fetch_first_party(url, source), None)
            except Exception as error:
                fetch_cache[key] = (None, error)
        result, error = fetch_cache[key]
        if error is not None:
            raise error
        return result

    for target in targets:
        game = str(target.get("game") or "").strip()
        game_policy = (policy.get("games") or {}).get(game) or {}
        if game_policy.get("enabled") is not True:
            continue
        aliases = [game] + [str(x) for x in (target.get("aliases") or []) if str(x).strip()]
        supplemental = [
            str(x).strip() for x in (game_policy.get("supplementalSources") or []) if str(x).strip()
        ]
        requested = list(dict.fromkeys(comparison_sources + supplemental))
        game_result = {"game": game, "sources": [], "standardConfirmed": 0}

        for source_id in requested:
            if source_id not in sources:
                review.append({
                    "game": game, "source": source_id, "reason": "unregistered_source",
                    "checkedAt": checked_at
                })
                continue
            source = sources[source_id]
            is_standard = source_id in comparison_sources
            current_rows = [
                r for r in rows
                if str(r.get("game") or "") == game and str(r.get("site") or "") == source_id
            ]
            urls = []
            for u in ((target.get("known_urls_by_source") or {}).get(source_id) or []):
                if source_host_allowed(u, source):
                    urls.append(u)
            for r in current_rows:
                u = str(r.get("url") or "")
                if u and source_host_allowed(u, source):
                    urls.append(u)

            listing_errors = []
            discovered = []
            listing_limit = max(0, min(2, int(source.get("direct_listing_limit", 2))))
            detail_limit = max(0, min(6, int(source.get("direct_detail_limit", 6))))
            for listing_url in (source.get("direct_listing_urls") or [])[:listing_limit]:
                try:
                    raw, final_url = fetch_once(listing_url, source)
                    if target_present(visible_text(raw), aliases):
                        discovered.extend(discover_detail_links(raw, final_url, source, aliases, limit=6))
                except Exception as e:
                    listing_errors.append(str(e)[:220])
            urls.extend(discovered)
            deduped_urls = []
            seen_identities = set()
            for candidate_url in urls:
                exact = exact_url_key(candidate_url)
                identity = offer_identity_key(exact, source_id)
                if not exact or not identity or identity in seen_identities:
                    continue
                seen_identities.add(identity)
                deduped_urls.append(exact)
            urls = deduped_urls[:detail_limit]

            source_result = {
                "source": source_id,
                "standard": is_standard,
                "knownOrDiscoveredUrls": len(urls),
                "confirmedOffers": 0,
                "updatedRows": 0,
                "reviewRequired": 0,
            }
            if len(deduped_urls) > detail_limit:
                review.append({
                    "game": game, "source": source_id, "reason": "detail_limit_reached",
                    "deferredCount": len(deduped_urls) - detail_limit,
                    "checkedAt": checked_at,
                })
                source_result["reviewRequired"] += 1

            if not urls:
                review.append({
                    "game": game, "source": source_id, "reason": "discovery_required",
                    "listingErrors": listing_errors, "checkedAt": checked_at
                })
                source_result["reviewRequired"] += 1
                source_result["state"] = "review_required"
                game_result["sources"].append(source_result)
                continue

            for url in urls:
                try:
                    detail = inspect_detail(url, source, aliases, fetcher=fetch_once)
                except Exception as e:
                    review.append({
                        "game": game, "source": source_id, "url": url,
                        "reason": "fetch_failed", "error": str(e)[:240], "checkedAt": checked_at
                    })
                    source_result["reviewRequired"] += 1
                    continue

                evidence = detail.get("sourceEvidence")
                if evidence is not None:
                    existing = row_by_identity.get((game, source_id, offer_identity_key(url, source_id)))
                    item = {"game": game, "source": source_id, "url": detail["url"],
                            "reason": "structured_offer_review_required" if evidence["state"] == "parsed"
                            else evidence.get("reason", "source_structure_review_required"),
                            "sourceEvidence": evidence, "checkedAt": checked_at}
                    if existing is not None:
                        item["storedPlatform"] = existing.get("platform") or ""
                        item["storedReward"] = existing.get("reward") or ""
                        if evidence["state"] == "parsed":
                            item["platformMatches"] = evidence["platform"] == existing.get("platform")
                            item["requiredChecks"] = ["reward_unit_conversion", "complete_terms_vs_published_row"]
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

        game_result["standardTotal"] = len(comparison_sources)
        game_result["comparisonReady"] = (
            game_result["standardConfirmed"] >= int(policy.get("minimumConfirmedSourcesForComparison") or 2)
        )
        results.append(game_result)

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "phase": "DIRECT_COMPARISON_REFRESH_V1",
        "checkedAt": checked_at,
        "comparisonSources": comparison_sources,
        "apiCalls": 0,
        "publishedRewardChanges": changed,
        "refreshedRows": 0,
        "reviewCount": len(review),
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
        "items": review,
    }
    tmp2 = REVIEW.with_suffix(".json.tmp")
    tmp2.write_text(json.dumps(review_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp2.replace(REVIEW)

    print("Direct comparison refresh complete")
    print("API calls: 0")
    print("Reward changes:", changed)
    print("Review items:", len(review))
    for g in results:
        print(f"{g['game']}: standard confirmed {g['standardConfirmed']}/{g['standardTotal']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
