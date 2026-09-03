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
from urllib.error import HTTPError, URLError
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
    """Review-only parser for COINCOME detail pages.

    It intentionally refuses publication. A page must bind exact URL identity,
    target name, one displayed yen-equivalent reward, one explicit app OS and a
    complete conditions block before it is useful as structured review evidence.
    """
    try:
        offer_id = coincome_offer_id(requested_url)
        if coincome_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [n for n in doc.find(tag="link")
                      if "canonical" in n.attrs.get("rel", "").split()]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            canonical_url = urljoin(final_url, canonicals[0].attrs.get("href", ""))
            if coincome_offer_id(canonical_url) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        text = visible_text(raw)
        if not target_present(text, aliases):
            if any(marker in text for marker in ("ページが見つかりません", "404 Not Found", "Not Found")):
                return {"state": "unavailable", "reason": "source_offer_unavailable",
                        "offerId": offer_id}
            raise ValueError("offer_title_mismatch")

        positions = []
        low = text.casefold()
        for alias in aliases:
            value = str(alias or "").strip()
            if not value:
                continue
            pos = low.find(value.casefold())
            if pos >= 0:
                positions.append((pos, value))
        if not positions:
            raise ValueError("offer_title_mismatch")
        start, matched_alias = min(positions, key=lambda item: item[0])

        header_tail = text[start:start + 1800]
        header_end_candidates = [
            header_tail.find(marker) for marker in ("ストア概要", "概要")
            if header_tail.find(marker) >= 0
        ]
        if not header_end_candidates:
            raise ValueError("missing_offer_header_boundary")
        header = header_tail[:min(header_end_candidates)]
        if len(header) < len(matched_alias):
            raise ValueError("missing_offer_header")

        displayed = []
        for match in re.finditer(r"(?<![0-9,])([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)\s*円", header):
            amount = int(match.group(1).replace(",", ""))
            if 0 < amount < 1_000_000:
                displayed.append(amount)
        unique_displayed = sorted(set(displayed))
        if len(unique_displayed) != 1:
            raise ValueError("ambiguous_displayed_reward")
        reward_yen = unique_displayed[0]

        condition_start = text.find("適用端末", start)
        if condition_start < 0:
            raise ValueError("incomplete_offer_terms")
        condition_end_candidates = [
            x for x in (
                text.find("リンクをコピーする", condition_start),
                text.find("© COINCOME", condition_start),
            ) if x >= 0
        ]
        if not condition_end_candidates:
            raise ValueError("incomplete_offer_terms")
        terms = text[condition_start:min(condition_end_candidates)].strip()

        required = ("適用端末", "キャッシュバック条件", "承認条件", "ポイント獲得条件", "否認条件")
        positions = [terms.find(marker) for marker in required]
        if any(pos < 0 for pos in positions) or positions != sorted(positions):
            raise ValueError("incomplete_offer_terms")

        pre_terms = text[start:condition_start]
        os_labels = sorted(set(re.findall(r"(?<![A-Za-z])(iOS|Android)(?![A-Za-z])", pre_terms, re.I)))
        normalized_os = {"ios": "iOS", "android": "Android"}
        platforms = sorted({normalized_os[label.casefold()] for label in os_labels})
        if len(platforms) != 1:
            raise ValueError("ambiguous_offer_platform")

        summary = re.sub(r"\s+", " ", header).strip()
        payload = {
            "offerId": offer_id,
            "name": matched_alias,
            "platform": platforms[0],
            "displayedRewardYen": reward_yen,
            "rewardUnit": "JPY-equivalent",
            "headerText": summary,
            "termsText": terms,
        }
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()
        return {"state": "parsed", "parserVersion": "coincome-detail-review-v1",
                **payload, "evidenceFingerprint": fingerprint}
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def moppy_offer_id(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname != "pc.moppy.jp"
            or p.username is not None or p.password is not None or p.port not in {None, 443}
            or p.path != "/ad/detail.php"):
        raise ValueError("unexpected_offer_url")
    query = parse_qs(p.query, keep_blank_values=False)
    if any(key not in {"site_id", "s_id"} for key in query):
        raise ValueError("ambiguous_offer_identity")
    values = []
    for key in ("site_id", "s_id"):
        values.extend(query.get(key) or [])
    if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
        raise ValueError("ambiguous_offer_identity")
    return values[0]


def inspect_moppy_offer(raw, requested_url, final_url, aliases):
    """Review-only parser for the public Moppy offer shell.

    Moppy explicitly states that the POINT GET destination can contain the
    applicable reward/conditions when they differ from the shell page. This
    parser therefore fingerprints shell evidence but never authorizes refresh.
    """
    try:
        offer_id = moppy_offer_id(requested_url)
        if moppy_offer_id(final_url) != offer_id:
            raise ValueError("redirected_to_different_offer")

        doc = EvidenceHTML(raw).root
        canonicals = [n for n in doc.find(tag="link")
                      if "canonical" in n.attrs.get("rel", "").split()]
        if len(canonicals) > 1:
            raise ValueError("missing_or_ambiguous_offer_structure")
        if canonicals:
            if moppy_offer_id(urljoin(final_url, canonicals[0].attrs.get("href", ""))) != offer_id:
                raise ValueError("canonical_offer_mismatch")

        title = evidence_text(one(doc.find(tag="h1")))
        if not target_present(title, aliases):
            raise ValueError("offer_title_mismatch")
        platforms = sorted(set(re.findall(r"(iOS|Android)", title, re.I)))
        normalized = {"ios": "iOS", "android": "Android"}
        platform_values = sorted({normalized[value.casefold()] for value in platforms})
        if len(platform_values) != 1:
            raise ValueError("ambiguous_offer_platform")
        platform = platform_values[0]

        text = visible_text(raw)
        start = text.find(title)
        if start < 0:
            raise ValueError("missing_offer_header")
        tail = text[start:start + 2200]
        boundaries = [
            tail.find(marker) for marker in ("ポイ活応援サービス", "ポイント獲得条件")
            if tail.find(marker) >= 0
        ]
        if not boundaries:
            raise ValueError("missing_offer_header_boundary")
        header = tail[:min(boundaries)]

        rewards = []
        for match in re.finditer(r"(?<![0-9,])([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)\s*P(?![A-Za-z])", header):
            amount = int(match.group(1).replace(",", ""))
            if 0 < amount < 1_000_000:
                rewards.append(amount)
        unique_rewards = sorted(set(rewards))
        if len(unique_rewards) != 1:
            raise ValueError("ambiguous_displayed_reward")
        reward_points = unique_rewards[0]

        if "1ポイント=1円" not in text:
            raise ValueError("unit_conversion_review_required")

        terms_start = text.find("■獲得条件", start)
        if terms_start < 0:
            raise ValueError("incomplete_offer_terms")
        terms_end = text.find("広告概要", terms_start)
        if terms_end < 0:
            raise ValueError("incomplete_offer_terms")
        terms = text[terms_start:terms_end].strip()
        if "成果受付期間" not in terms:
            raise ValueError("incomplete_offer_terms")
        if not any(marker in terms for marker in ("■注意事項", "■却下条件", "却下条件")):
            raise ValueError("incomplete_offer_terms")
        if "POINT GET" not in text or "遷移" not in text:
            raise ValueError("downstream_terms_review_required")

        payload = {
            "offerId": offer_id,
            "name": title,
            "platform": platform,
            "displayedRewardPoints": reward_points,
            "rewardUnit": "P",
            "baseYenPerPoint": 1,
            "downstreamTermsRequired": True,
            "headerText": re.sub(r"\s+", " ", header).strip(),
            "termsText": terms,
        }
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True).encode("utf-8")).hexdigest()
        return {"state": "parsed", "parserVersion": "moppy-shell-review-v1",
                **payload, "evidenceFingerprint": fingerprint}
    except (ValueError, TypeError, RecursionError) as error:
        return {"state": "review_required", "reason": str(error)[:120]}


def inspect_detail(url, source, aliases, fetcher=None):
    raw, final_url = (fetcher or fetch_first_party)(url, source)
    structured_parsers = {
        "warau": inspect_warau_offer,
        "chobirich": inspect_chobirich_offer,
        "coincome": inspect_coincome_offer,
        "moppy": inspect_moppy_offer,
    }
    if source.get("id") in structured_parsers:
        evidence = structured_parsers[source["id"]](raw, url, final_url, aliases)
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


def main():
    try:
        approvals = load_refresh_approvals()
    except (OSError, ValueError, TypeError):
        print("ERROR: approval registry is unreadable or invalid; no refresh performed", file=sys.stderr)
        return 2
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

    original_published = PUBLISHED.read_bytes() if PUBLISHED.exists() else None
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
    refreshed = set()
    publication_changed = False
    fetch_cache = {}

    def fetch_once(url, source):
        key = (source.get("id"), exact_url_key(url))
        if key not in fetch_cache:
            try:
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
            if source.get("scheduled_fetch_enabled", True) is not True:
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
                    listing_errors.append({"url": listing_url, "error": summarize_fetch_error(e)})
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
                    "listingErrors": [item["error"] for item in listing_errors], "checkedAt": checked_at
                })
                source_result["reviewRequired"] += 1
                source_result["state"] = "review_required"
                game_result["sources"].append(source_result)
                continue

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
                    detail = inspect_detail(url, source, aliases, fetcher=fetch_once)
                except Exception as e:
                    review.append({
                        "game": game, "source": source_id, "url": url,
                        "reason": "fetch_failed", "error": summarize_fetch_error(e), "checkedAt": checked_at
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
                            reason = (approved_refresh_reason(existing, evidence,
                                approvals.get(existing.get("offerKey")), checked_at)
                                if source_id == "warau" else "source_refresh_not_enabled")
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

        game_result["standardTotal"] = len(comparison_sources)
        game_result["comparisonReady"] = (
            game_result["standardConfirmed"] >= int(policy.get("minimumConfirmedSourcesForComparison") or 2)
        )
        results.append(game_result)

    if publication_changed:
        if not PUBLISHED.exists() or PUBLISHED.read_bytes() != original_published:
            print("ERROR: published data changed during refresh; refusing to overwrite", file=sys.stderr)
            return 2
        write_published(rows)

    STATUS.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "phase": "DIRECT_COMPARISON_REFRESH_V1",
        "checkedAt": checked_at,
        "comparisonSources": comparison_sources,
        "apiCalls": 0,
        "publishedRewardChanges": changed,
        "refreshedRows": len(refreshed),
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
