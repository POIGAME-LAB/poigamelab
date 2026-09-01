#!/usr/bin/env python3
"""PHASE 1 Firecrawl probe for POIGAME LAB.

Goal:
  Registered point sites -> Firecrawl direct scrape + offerwall traversal + domain-restricted search
  -> collect only Township evidence -> Gemini extraction/verification -> JSON.

No user-specific offerwall URLs or API keys are written to output.
Requires FIRECRAWL_API_KEY and GEMINI_API_KEY in .env or environment.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from html import unescape
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "point_sources.json"
RAW_OUT = ROOT / "data" / "township_firecrawl_candidates.json"
OUT = ROOT / "data" / "township_firecrawl_result.json"

def slugify_game(name):
    table = {"Township": "township", "きのこ伝説": "kinoko-densetsu", "メメントモリ": "memento-mori", "ワーキングヒーロー": "working-hero"}
    if name in table:
        return table[name]
    raw = name or "game"
    x = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if x and raw.isascii():
        return x
    import hashlib
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{x + '-' if x else 'game-'}{digest}"

def configure_output_paths(cfg):
    global RAW_OUT, OUT
    slug = slugify_game((cfg.get("target") or {}).get("game") or "game")
    RAW_OUT = ROOT / "data" / f"{slug}_firecrawl_candidates.json"
    OUT = ROOT / "data" / f"{slug}_firecrawl_result.json"

CACHE_DIR = ROOT / "data" / "cache"

FIRECRAWL_CALL_LIMIT = max(1, min(2, int(os.getenv("FIRECRAWL_CALL_LIMIT", "2") or "2")))
FIRECRAWL_CALL_SEMAPHORE = threading.BoundedSemaphore(FIRECRAWL_CALL_LIMIT)


CURRENT_TARGET = {"game": "Township", "aliases": ["Township", "タウンシップ"]}

def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def cache_path_for(source_id, url):
    import hashlib
    key = hashlib.sha256((source_id + "\n" + offer_identity_url(url)).encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / f"{source_id}_{key}.json"


def load_candidate_cache(source_id, url, max_age_seconds):
    if max_age_seconds <= 0:
        return None
    p = cache_path_for(source_id, url)
    if not p.exists():
        return None
    try:
        age = time.time() - p.stat().st_mtime
        if age > max_age_seconds:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        c = data.get("candidate")
        if isinstance(c, dict) and c.get("url"):
            c = dict(c)
            c["kind"] = "known_official_cache"
            c.setdefault("metadata", {})["cacheAgeSeconds"] = round(age, 1)
            return c
    except Exception:
        return None
    return None


def save_candidate_cache(source_id, url, candidate):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path_for(source_id, url)
    safe = dict(candidate)
    # Public official locator is retained; transient links are not needed in cache.
    safe["links"] = []
    p.write_text(json.dumps({
        "savedAt": now_iso(),
        "candidate": safe,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post_json(url, payload, headers=None, timeout=90):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", **(headers or {})}
    req = Request(url, data=data, headers=h, method="POST")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def direct_http_get(url, source, timeout=15, max_bytes=1200000):
    """Fetch one allowlisted first-party page without Firecrawl.

    The response is bounded and only registered point-site hosts are accepted.
    This function never follows or persists offerwall/session URLs.
    """
    if not registered_host(url, source, {"offerwall_domains_discovered": []}):
        raise ValueError("direct URL is outside registered first-party domains")
    # V41: app-offer listings can be device-gated. Moppy explicitly serves
    # app-install ads through its smartphone-browser experience, so honor the
    # source registry's mobile flag instead of always identifying as a bot/PC.
    # This remains a plain first-party GET; no login, cookie, or session token
    # is supplied or persisted.
    if source.get("mobile"):
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        )
        device_mode = "mobile"
    else:
        user_agent = "Mozilla/5.0 (compatible; POIGAMELAB/1.0; +https://poigamelab.com/)"
        device_mode = "desktop"
    req = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
    })
    with urlopen(req, timeout=timeout) as r:
        final_url = r.geturl() if hasattr(r, "geturl") else url
        if not registered_host(final_url, source, {"offerwall_domains_discovered": []}):
            raise ValueError("direct HTTP redirect left registered first-party domains")
        data = r.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
            truncated = True
        else:
            truncated = False
        charset = None
        try:
            charset = r.headers.get_content_charset()
        except Exception:
            charset = None
    text = data.decode(charset or "utf-8", errors="replace")
    return text, {"bytes": len(data), "truncated": truncated, "deviceMode": device_mode}


def html_to_visible_text(raw_html):
    text = re.sub(r"(?is)<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)>", " ", raw_html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def html_title(raw_html):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html or "")
    return html_to_visible_text(m.group(1)) if m else ""


class _MiniHtmlNode:
    __slots__ = ("tag", "attrs", "parent", "children", "text")

    def __init__(self, tag="", attrs=None, parent=None):
        self.tag = (tag or "").lower()
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children = []
        self.text = []


class _MiniHtmlTreeParser(HTMLParser):
    """Small dependency-free tree used only for bounded listing-card context."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _MiniHtmlNode("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _MiniHtmlNode(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _MiniHtmlNode(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack[-1].tag not in {"script", "style", "noscript", "svg"}:
            self.stack[-1].text.append(data)


def _node_visible_text(node, limit=2600):
    parts = []
    total = 0
    stack = [node]
    while stack and total < limit:
        cur = stack.pop()
        for t in cur.text:
            if t:
                parts.append(t)
                total += len(t)
                if total >= limit:
                    break
        if total >= limit:
            break
        stack.extend(reversed(cur.children))
    return re.sub(r"\s+", " ", unescape(" ".join(parts))).strip()[:limit]


def _iter_nodes(node):
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        stack.extend(reversed(cur.children))


def _detail_like_first_party_url(url, source):
    """Require a first-party URL shape that plausibly selects one offer.

    This is a discovery guard only. The fetched detail page must independently
    contain the target name, and the existing V20 exact-offer identity gate
    still decides publication eligibility.
    """
    try:
        u = urlparse(url)
    except Exception:
        return False
    path = (u.path or "").lower()
    query = (u.query or "").lower()
    configured = [str(x).lower() for x in (source.get("direct_detail_url_hints") or []) if x]
    if configured and any(h in (path + "?" + query) for h in configured):
        return True
    if re.search(r"(?:^|[?&])(?:point_id|site_id|s_id|itemid|campaign_id|campaignid|id)=", query):
        return True
    generic_hints = ("pointentrance", "/ad_details/", "/campaigns/details/", "/ad/detail", "/campaign/detail")
    return any(h in path for h in generic_hints)


def _generic_detail_anchor_label(label):
    x = re.sub(r"\s+", "", (label or "").casefold())
    if not x:
        return True
    generic = {
        "詳細", "詳細を見る", "詳しく見る", "もっと見る", "こちら", "参加", "申込", "申し込む",
        "お申し込み", "ポイント獲得", "獲得", "ios", "iphone", "android",
        "check", "view", "detail", "details", "more",
    }
    return x in {re.sub(r"\s+", "", g.casefold()) for g in generic}


def target_adjacent_first_party_links(raw_html, base_url, source, aliases, limit=8):
    """Find target-associated official detail links, including image-only cards.

    V38 only accepted anchors whose *own label* contained the game name. Real
    point-site cards often make an image or the whole card clickable while the
    game title is a sibling element. V39 therefore inspects the smallest nearby
    card/container around each first-party detail-shaped anchor. A candidate is
    still fetched and must independently confirm the target before it can enter
    the verifier, so surrounding-card matching cannot create publishable false
    positives by itself.
    """
    out = []
    seen = set()

    def add_url(href):
        if not href:
            return False
        absolute = urljoin(base_url, unescape(href).strip())
        if not registered_host(absolute, source, {"offerwall_domains_discovered": []}):
            return False
        identity = offer_identity_url(absolute)
        if identity in seen:
            return False
        seen.add(identity)
        out.append(absolute)
        return len(out) >= limit

    # Keep the strongest V38 path first: explicit target label on the anchor.
    for m in re.finditer(r"(?is)<a\b[^>]*?href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", raw_html or ""):
        label = html_to_visible_text(m.group(3))
        if text_has_target(label, aliases) and add_url(m.group(2)):
            return out

    # Card-context path for image-only / whole-card links.
    try:
        parser = _MiniHtmlTreeParser()
        parser.feed(raw_html or "")
        parser.close()
    except Exception:
        return out

    card_tags = {"li", "article", "section", "div", "tr", "td", "dd", "dl"}
    for node in _iter_nodes(parser.root):
        if node.tag != "a":
            continue
        href = (node.attrs.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(base_url, href)
        if not registered_host(absolute, source, {"offerwall_domains_discovered": []}):
            continue
        if not _detail_like_first_party_url(absolute, source):
            continue
        anchor_label = _node_visible_text(node, limit=180)
        if not _generic_detail_anchor_label(anchor_label):
            # A non-generic label naming something else is strong evidence that
            # this anchor belongs to a different offer, even if a target is
            # mentioned elsewhere on the page.
            continue

        # Walk only a few levels and use the *smallest* target-bearing container.
        # This prevents a page-level target mention from blessing unrelated links.
        cur = node.parent
        depth = 0
        matched = False
        while cur is not None and depth < 6:
            if cur.tag in card_tags:
                context = _node_visible_text(cur, limit=2200)
                if len(context) <= 1800 and text_has_target(context, aliases):
                    matched = True
                    break
                # Empty/single-child wrappers around an image/button may be
                # crossed. Once a container branches into multiple elements
                # without the target, treat it as this anchor's own non-target
                # card and never climb to a page/listing-level target mention.
                if len(cur.children) > 1:
                    break
            cur = cur.parent
            depth += 1
        if matched and add_url(href):
            break
    return out


def tavily_official_detail_discovery(source, aliases, api_key=None, fetcher=None, searcher=None, limit=4):
    """Discover indexed first-party offer detail URLs, then verify them directly.

    Search results are discovery hints only: titles/snippets never become evidence.
    Every URL must be registered first-party, detail-shaped, and its official page
    must independently contain the target before a candidate is returned.
    """
    api_key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")
    if fetcher is None:
        fetcher = direct_http_get
    diag = {"attempted": bool(api_key), "searchCompleted": False, "resultUrls": 0, "eligibleUrls": 0, "confirmed": 0, "details": [], "absenceAuthoritative": False, "coverage": "indexed_public_official_details"}
    if not api_key:
        diag["skipped"] = "TAVILY_API_KEY unavailable"
        return [], diag
    target = CURRENT_TARGET.get("game") or (aliases[0] if aliases else "")
    domains = [d for d in (source.get("search_domains") or []) if d]
    site = domains[-1] if domains else (urlparse(source.get("start_url") or "").hostname or "")
    query = f'"{target}" site:{site} ad detail'
    try:
        if searcher is None:
            payload = {"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 8, "include_answer": False, "include_raw_content": False}
            response = post_json("https://api.tavily.com/search", payload, timeout=45)
        else:
            response = searcher(query)
        results = response.get("results") or []
        diag["searchCompleted"] = True
    except Exception as e:
        diag["error"] = str(e)[:240]
        return [], diag
    diag["resultUrls"] = len(results)
    candidates=[]; seen=set()
    for item in results:
        url=str((item or {}).get("url") or "").strip()
        if not url or not registered_host(url, source, {"offerwall_domains_discovered": []}) or not _detail_like_first_party_url(url, source):
            continue
        identity=offer_identity_url(url)
        if identity in seen:
            continue
        seen.add(identity); diag["eligibleUrls"] += 1
        if len(seen) > max(1, min(6, int(limit or 4))):
            break
        try:
            raw, meta = fetcher(url, source)
            visible=html_to_visible_text(raw); hit=text_has_target(visible, aliases)
            diag["details"].append({"identityUrl": identity, "ok": True, "targetFound": hit, **meta})
            if not hit:
                continue
            candidates.append(compact_candidate(source, "indexed_official_detail", url, title=html_title(raw), markdown=visible, links=[], metadata={"targetFound": True, "retrieval": "tavily_discovery_direct_verify"}))
            diag["confirmed"] += 1
        except Exception as e:
            diag["details"].append({"identityUrl": identity, "ok": False, "error": str(e)[:240]})
    return candidates, diag


def direct_first_party_collect(source, aliases, cfg, fetcher=None):
    """V38 direct-first research path for stable official listing pages.

    Listing pages are discovery evidence only. Publication-capable candidates
    are created only after a target-adjacent first-party detail page is fetched
    and independently confirms the target text.
    """
    if fetcher is None:
        fetcher = direct_http_get
    urls = list(source.get("direct_listing_urls") or [])
    if not urls and source.get("start_url"):
        urls = [source["start_url"]]
    urls = urls[:max(1, min(3, int(source.get("direct_listing_limit", 2) or 2)))]
    detail_limit = max(1, min(6, int(source.get("direct_detail_limit", 4) or 4)))
    candidates = []
    diag = {"attempted": bool(urls), "listings": [], "details": [], "candidateCount": 0}
    detail_urls = []
    seen_details = set()

    for listing_url in urls:
        try:
            raw, meta = fetcher(listing_url, source)
            visible = html_to_visible_text(raw)
            hit = text_has_target(visible, aliases)
            links = target_adjacent_first_party_links(raw, listing_url, source, aliases, limit=detail_limit) if hit else []
            diag["listings"].append({"ok": True, "targetFound": hit, "detailLinks": len(links), **meta})
            for u in links:
                if u not in seen_details and len(detail_urls) < detail_limit:
                    seen_details.add(u); detail_urls.append(u)
        except Exception as e:
            diag["listings"].append({"ok": False, "error": str(e)[:240]})

    for detail_url in detail_urls:
        try:
            raw, meta = fetcher(detail_url, source)
            visible = html_to_visible_text(raw)
            hit = text_has_target(visible, aliases)
            diag["details"].append({"identityUrl": offer_identity_url(detail_url), "ok": True, "targetFound": hit, **meta})
            if not hit:
                continue
            candidates.append(compact_candidate(
                source, "direct_official_detail", detail_url,
                title=html_title(raw), markdown=visible, links=[],
                metadata={"targetFound": True, "retrieval": "direct_first_party_http"},
            ))
        except Exception as e:
            diag["details"].append({"identityUrl": offer_identity_url(detail_url), "ok": False, "error": str(e)[:240]})

    diag["candidateCount"] = len(candidates)
    diag["allListingsFetched"] = bool(urls) and all(x.get("ok") for x in diag["listings"])
    return candidates, diag


def firecrawl_post(key, endpoint, payload, timeout=120, attempts=3):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            with FIRECRAWL_CALL_SEMAPHORE:
                return post_json(
                    f"https://api.firecrawl.dev/v2/{endpoint}",
                    payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=timeout,
                )
        except HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504) or attempt == attempts:
                raise
        except (URLError, TimeoutError) as e:
            last = e
            if attempt == attempts:
                raise
        time.sleep(1.5 * attempt)
    raise last


def text_has_target(text, aliases):
    low = (text or "").casefold()
    return any(a.casefold() in low for a in aliases)


def normalize_links(links):
    out = []
    for item in links or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            u = item.get("url") or item.get("href")
            if u:
                out.append(u)
    return out



def registered_host(url, source, cfg):
    try:
        host=(urlparse(url).hostname or "").lower()
    except Exception:
        return False
    domains=[d.lower() for d in (source.get("search_domains") or [])]
    domains += [d.lower() for d in (cfg.get("offerwall_domains_discovered") or [])]
    return any(host == d or host.endswith("."+d) for d in domains)


def extract_target_adjacent_links(markdown, aliases, window=320):
    """Return markdown links explicitly associated with the target game.

    This intentionally accepts opaque detail URLs (for example ?id=123) only
    when the link itself or its nearby text names Township. It lets provider
    listing pages reveal a first-party detail URL without blindly crawling
    every link on the page.
    """
    text = markdown or ""
    if not text:
        return []
    found = []
    seen = set()
    # Standard Markdown links produced by Firecrawl.
    for m in re.finditer(r'\[([^\]]*)\]\((https?://[^)\s]+)\)', text, flags=re.I):
        label, url = m.group(1), m.group(2)
        lo = max(0, m.start() - window)
        hi = min(len(text), m.end() + window)
        context = label + "\n" + text[lo:hi]
        if not text_has_target(context, aliases):
            continue
        if url not in seen:
            seen.add(url)
            found.append(url)

    # Some pages expose a raw URL on the same line/block instead of Markdown.
    # Only retain it if the short surrounding context contains the target.
    for m in re.finditer(r'https?://[^\s<>"\']+', text, flags=re.I):
        url = m.group(0).rstrip(').,;]')
        lo = max(0, m.start() - window)
        hi = min(len(text), m.end() + window)
        if not text_has_target(text[lo:hi], aliases):
            continue
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def extract_urls_from_text(text):
    return re.findall(r'https?://[^\\s<>"\\)\\]]+', text or "")


def follow_candidate_links(key, source, seeds, aliases, cfg, limit=18, skip_urls=None):
    """Follow likely official detail links one hop from collected evidence.

    Target-adjacent first-party links are highest priority, even when the URL
    itself is opaque. Generic URL-hint crawling remains a fallback.
    """
    target_urls = []
    generic_urls = []
    for c in seeds:
        md = c.get("markdown") or ""
        target_urls += extract_target_adjacent_links(md, aliases)
        generic_urls += normalize_links(c.get("links") or [])
        generic_urls += extract_urls_from_text(md + "\n" + (c.get("description") or ""))

    seen = set(skip_urls or [])
    picked = []
    picked_reason = {}

    # Strong path: only target-adjacent links, and only on the registered
    # source/known offerwall domains. First-party gate still decides publishing.
    def crawlable_detail_url(u):
        raw=(u or "").lower()
        path=(urlparse(u).path or "").lower()
        if ")](" in raw or "](" in raw:
            return False
        return not re.search(r"\.(?:png|jpe?g|gif|webp|svg|ico|css|js|woff2?|mp4|webm)(?:$|[/?#])", path + "/")

    for u in target_urls:
        if not u or u in seen or not registered_host(u, source, cfg) or not crawlable_detail_url(u):
            continue
        seen.add(u)
        picked.append(u)
        picked_reason[u] = "target_adjacent"
        if len(picked) >= limit:
            break

    # Conservative fallback for generic links.
    hints=("detail","point","app","game","campaign","offer","entrance","smartphone","land")
    if len(picked) < limit:
        for u in generic_urls:
            if not u or u in seen or not registered_host(u, source, cfg) or not crawlable_detail_url(u):
                continue
            low=u.lower()
            if not any(h in low for h in hints):
                continue
            seen.add(u)
            picked.append(u)
            picked_reason[u] = "url_hint"
            if len(picked)>=limit:
                break

    out=[]; diag=[]
    for u in picked:
        temp=dict(source); temp["start_url"]=u
        try:
            c=direct_scrape(key,temp,aliases)
            hit=bool((c.get("metadata") or {}).get("targetFound"))
            c["kind"]="followed_detail"
            c.setdefault("metadata", {})["followReason"] = picked_reason.get(u)
            diag.append({
                "url": sanitize_url(u),
                "identityUrl": offer_identity_url(u),
                "ok": True,
                "targetFound": hit,
                "reason": picked_reason.get(u),
            })
            if hit:
                out.append(c)
        except Exception as e:
            diag.append({
                "url": sanitize_url(u),
                "identityUrl": offer_identity_url(u),
                "ok": False,
                "reason": picked_reason.get(u),
                "error": str(e)[:240],
            })
    return out,diag

def compact_candidate(source, kind, url, title="", description="", markdown="", links=None, metadata=None):
    # Geminiに十分な証拠を渡しつつ、巨大ページでトークンを浪費しない。
    return {
        "source_id": source["id"],
        "source_name": source["name"],
        "kind": kind,
        "url": url,
        "title": title or "",
        "description": description or "",
        "markdown": (markdown or "")[:24000],
        "links": normalize_links(links)[:300],
        "metadata": metadata or {},
    }


def direct_scrape(key, source, aliases):
    payload = {
        "url": source["start_url"],
        "formats": ["markdown", "links"],
        "onlyMainContent": False,
        "mobile": bool(source.get("mobile", True)),
        "waitFor": 2500,
        "timeout": 60000,
        "location": {"country": "JP", "languages": ["ja-JP", "ja"]},
        "blockAds": True,
        "maxAge": int(os.getenv("FIRECRAWL_MAX_AGE_MS", "1800000")),
    }
    res = firecrawl_post(key, "scrape", payload)
    data = res.get("data") or {}
    md = data.get("markdown") or ""
    links = data.get("links") or []
    hit = text_has_target(md, aliases) or any(text_has_target(x, aliases) for x in normalize_links(links))
    return compact_candidate(
        source,
        "direct_scrape",
        source["start_url"],
        title=(data.get("metadata") or {}).get("title", ""),
        description=(data.get("metadata") or {}).get("description", ""),
        markdown=md,
        links=links,
        metadata={**(data.get("metadata") or {}), "targetFound": hit},
    )


def domain_search(key, source, aliases):
    # 登録済みポイントサイト内だけを検索。英語/日本語の両表記で取りこぼしを減らす。
    terms = source.get("search_terms")
    if not terms:
        terms = list(dict.fromkeys((aliases or []) + ["StepUp"]))
    quoted = " OR ".join(f'"{x}"' for x in terms)
    query = f'({quoted}) {source["name"]}'
    payload = {
        "query": query,
        "limit": 12,
        "sources": ["web"],
        "includeDomains": source.get("search_domains") or [],
        "location": "Japan",
        "country": "JP",
        "timeout": 60000,
        "scrapeOptions": {
            "formats": ["markdown"],
            "onlyMainContent": True,
            "mobile": bool(source.get("mobile", True)),
            "waitFor": 1500,
            "location": {"country": "JP", "languages": ["ja-JP", "ja"]},
            "blockAds": True,
            "maxAge": int(os.getenv("FIRECRAWL_MAX_AGE_MS", "1800000")),
        },
    }
    res = firecrawl_post(key, "search", payload)
    data = res.get("data") or {}
    web_items = data.get("web") if isinstance(data, dict) else []
    out = []
    for x in web_items or []:
        md = x.get("markdown") or ""
        title = x.get("title") or ""
        desc = x.get("description") or ""
        url = x.get("url") or (x.get("metadata") or {}).get("sourceURL") or ""
        hay = "\n".join([title, desc, md, url])
        if not text_has_target(hay, aliases):
            continue
        out.append(compact_candidate(
            source,
            "domain_search",
            url,
            title=title,
            description=desc,
            markdown=md,
            links=x.get("links") or [],
            metadata=x.get("metadata") or {},
        ))
    return out



def sanitize_url(url):
    """Remove query/fragment before persisting a URL."""
    try:
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        return url


def offer_identity_url(url):
    """Canonical URL used only for offer deduplication.

    Preserve stable parameters that select a public offer while removing
    tracking/session parameters. This prevents OS-specific offers sharing the
    same path from being collapsed (e.g. Warau point_id).
    """
    try:
        from urllib.parse import parse_qsl, urlencode, urlunparse
        u = urlparse(url)
        keep = {"point_id", "site_id", "s_id", "itemid", "campaign_id", "campaignid", "id"}
        params = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k.lower() in keep]
        query = urlencode(sorted(params))
        return urlunparse((u.scheme.lower(), u.netloc.lower(), u.path, "", query, ""))
    except Exception:
        return url


def extract_labeled_links(markdown, labels, window=120):
    """Extract links whose visible label / nearby text names a provider hub.

    This is intentionally label-driven rather than URL-shape-driven because
    provider entry URLs often contain opaque/session parameters.
    """
    text = markdown or ""
    labels = [x for x in (labels or []) if x]
    if not text or not labels:
        return []
    out = []
    seen = set()
    for m in re.finditer(r'\[([^\]]*)\]\((https?://[^)\s]+)\)', text, flags=re.I):
        label, url = m.group(1), m.group(2)
        lo=max(0,m.start()-window); hi=min(len(text),m.end()+window)
        context=(label+"\n"+text[lo:hi]).lower()
        if not any(lbl.lower() in context for lbl in labels):
            continue
        if url not in seen:
            seen.add(url); out.append(url)
    return out


def discover_provider_hub_links(direct, source):
    """Find provider entry points such as ちょびリッチ's アプリランド.

    Full URLs remain runtime-only. Nothing with session/tracking parameters is
    written to diagnostics or candidate output.
    """
    labels = source.get("provider_hub_labels") or []
    if not labels:
        return []
    found = extract_labeled_links(direct.get("markdown") or "", labels)

    # If Firecrawl's markdown lost anchor labels, conservatively consider links
    # only when their URL contains a configured provider hint.
    hints=[x.lower() for x in (source.get("provider_url_hints") or [])]
    if hints:
        for url in normalize_links(direct.get("links") or []):
            low=url.lower()
            if any(h in low for h in hints):
                found.append(url)
    return list(dict.fromkeys(found))[:12]


def scrape_provider_hub(key, source, transient_url, aliases):
    """Scrape a provider hub using a transient URL but persist only sanitized data."""
    payload = {
        "url": transient_url,
        "formats": ["markdown", "links"],
        "onlyMainContent": False,
        "mobile": True,
        "waitFor": 3500,
        "timeout": 60000,
        "location": {"country": "JP", "languages": ["ja-JP", "ja"]},
        "blockAds": True,
        "maxAge": int(os.getenv("FIRECRAWL_MAX_AGE_MS", "1800000")),
    }
    res=firecrawl_post(key,"scrape",payload)
    data=res.get("data") or {}
    md=data.get("markdown") or ""
    links=normalize_links(data.get("links") or [])
    hit=text_has_target(md,aliases) or any(text_has_target(x,aliases) for x in links)
    host=(urlparse(transient_url).hostname or "").lower()
    safe_url=sanitize_url(transient_url)
    return compact_candidate(
        source,
        "provider_hub_scrape",
        safe_url,
        title=(data.get("metadata") or {}).get("title",""),
        description=(data.get("metadata") or {}).get("description",""),
        markdown=md if hit else "",
        links=[sanitize_url(x) for x in links] if hit else [],
        metadata={
            "targetFound": hit,
            "providerHubDomain": host,
            "providerHubLabel": source.get("provider_hub_labels") or [],
        },
    )


def discover_offerwall_links(direct, cfg):
    """Find known offerwall-domain links on the parent page. Full URLs stay memory-only."""
    domains = [d.lower() for d in (cfg.get("offerwall_domains_discovered") or [])]
    found = []
    for url in direct.get("links") or []:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            continue
        if any(host == d or host.endswith("." + d) for d in domains):
            found.append(url)
    # Keep order, avoid duplicate session links.
    return list(dict.fromkeys(found))[:30]


def scrape_offerwall(key, source, transient_url, aliases):
    payload = {
        "url": transient_url,
        "formats": ["markdown", "links"],
        "onlyMainContent": False,
        "mobile": True,
        "waitFor": 3500,
        "timeout": 60000,
        "location": {"country": "JP", "languages": ["ja-JP", "ja"]},
        "blockAds": True,
        "maxAge": int(os.getenv("FIRECRAWL_MAX_AGE_MS", "1800000")),
    }
    res = firecrawl_post(key, "scrape", payload)
    data = res.get("data") or {}
    md = data.get("markdown") or ""
    links = normalize_links(data.get("links") or [])
    hit = text_has_target(md, aliases) or any(text_has_target(x, aliases) for x in links)
    safe_url = sanitize_url(transient_url)
    return compact_candidate(
        source,
        "offerwall_scrape",
        safe_url,
        title=(data.get("metadata") or {}).get("title", ""),
        description=(data.get("metadata") or {}).get("description", ""),
        markdown=md if hit else "",
        links=[sanitize_url(x) for x in links] if hit else [],
        metadata={
            "targetFound": hit,
            "offerwallDomain": (urlparse(transient_url).hostname or "").lower(),
        },
    )

def verify_search_hits(key, source, search_hits, aliases, skip_urls=None):
    """Re-scrape URLs discovered by domain search as primary official evidence.
    Search finds the locator; this step reads the live official page again.
    """
    out, diag = [], []
    seen = set(skip_urls or [])
    for hit in search_hits[:8]:
        url = hit.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        temp = dict(source)
        temp["start_url"] = url
        try:
            c = direct_scrape(key, temp, aliases)
            found = bool((c.get("metadata") or {}).get("targetFound"))
            c["kind"] = "official_search_verified"
            diag.append({"url": url, "ok": True, "targetFound": found})
            if found:
                out.append(c)
        except Exception as e:
            # Keep the original Firecrawl search result as evidence even if
            # a second scrape is temporarily rejected by the site/API.
            diag.append({"url": url, "ok": False, "fallbackToSearch": True, "error": str(e)[:300]})
    return out, diag


def probe_known_pages(key, source, aliases):
    """Read stable official URLs concurrently, with process-wide Firecrawl cap=2."""
    ttl=int(os.getenv("POIGAMELAB_KNOWN_CACHE_SECONDS","1800") or "1800")
    attempts=max(1,min(2,int(os.getenv("POIGAMELAB_KNOWN_PAGE_ATTEMPTS","2") or "2")))
    retry_delay=float(os.getenv("POIGAMELAB_KNOWN_RETRY_DELAY","1.5") or "1.5")
    urls=list(source.get("known_target_urls") or [])
    page_workers=max(1,min(2,int(os.getenv("POIGAMELAB_KNOWN_PAGE_WORKERS","2") or "2")))

    def probe_one(index,url):
        cached=load_candidate_cache(source["id"],url,ttl)
        if cached is not None:
            hit=bool((cached.get("metadata") or {}).get("targetFound",True))
            d={"url":url,"ok":True,"targetFound":hit,"cache":"hit",
               "cacheAgeSeconds":(cached.get("metadata") or {}).get("cacheAgeSeconds")}
            return index,(cached if hit else None),d

        temp=dict(source); temp["start_url"]=url
        c=None; last_error=None; used_attempts=0
        for attempt in range(1,attempts+1):
            used_attempts=attempt
            try:
                c=direct_scrape(key,temp,aliases)
                break
            except Exception as e:
                last_error=e
                transient=any(code in str(e) for code in ("429","500","502","503","504"))
                if attempt < attempts and transient:
                    time.sleep(retry_delay)
                    continue
                break

        if c is not None:
            hit=bool((c.get("metadata") or {}).get("targetFound"))
            c["kind"]="known_official_probe"
            d={"url":url,"ok":True,"targetFound":hit,"cache":"miss","attempts":used_attempts}
            if hit:
                save_candidate_cache(source["id"],url,c)
                return index,c,d
            return index,None,d

        stale=load_candidate_cache(source["id"],url,365*24*3600)
        if stale is not None:
            stale.setdefault("metadata",{})["staleCacheFallback"]=True
            return index,stale,{"url":url,"ok":False,"cache":"stale_fallback","attempts":used_attempts,
                               "error":str(last_error)[:300]}
        return index,None,{"url":url,"ok":False,"cache":"miss","attempts":used_attempts,
                           "error":str(last_error)[:300]}

    results={}
    if len(urls)<=1 or page_workers==1:
        for i,u in enumerate(urls):
            results[i]=probe_one(i,u)[1:]
    else:
        with ThreadPoolExecutor(max_workers=page_workers,thread_name_prefix="poigamelab-known") as pool:
            futures={pool.submit(probe_one,i,u):i for i,u in enumerate(urls)}
            for fut in as_completed(futures):
                i,c,d=fut.result()
                results[i]=(c,d)

    out=[]; diag=[]
    for i in range(len(urls)):
        c,d=results[i]
        diag.append(d)
        if c is not None:
            out.append(c)
    return out,diag

def collect_firecrawl(key, cfg):
    """Bounded parallel collector.

    Each point site keeps its safe sequential workflow, while up to two sites
    can run at once. Publication rules are unchanged.
    """
    aliases = cfg["target"]["aliases"]
    sources = [s for s in cfg["sources"] if s.get("enabled", True)]
    requested_workers = int(os.getenv("FIRECRAWL_SOURCE_WORKERS", "2") or "2")
    workers = max(1, min(2, requested_workers))

    def collect_one(idx, source):
        source_started = time.monotonic()
        local_candidates = []
        diag = {
            "source_id": source["id"], "source_name": source["name"],
            "mode": "discovery", "direct": None, "direct_http": None, "indexed_official": None, "offerwalls": [], "provider_hubs": [],
            "known_pages": [], "search": None, "search_verified": [],
            "followed_details": [],
        }

        known, known_diag = probe_known_pages(key, source, aliases)
        diag["known_pages"] = known_diag
        local_candidates.extend(known)
        min_known = int(source.get("known_pages_sufficient", 1))
        partial_fast = bool(source.get("allow_partial_known_fast_path", False))
        known_fast_enough = bool(known) and (
            len(known) >= min_known or (partial_fast and len(known) >= 1)
        )
        if known_fast_enough and source.get("prefer_known_pages", True):
            diag["mode"] = "known_official_fast_path"
            diag["search"] = {
                "skipped": True,
                "reason": f"known official {CURRENT_TARGET.get('game') or 'target'} detail pages succeeded",
                "knownSuccess": len(known),
                "knownExpected": len(source.get("known_target_urls") or []),
                "partialAccepted": bool(partial_fast and len(known) < min_known),
            }
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag

        # V38: stable first-party HTTP before any Firecrawl call. Detail pages
        # must independently contain the target before becoming candidates.
        direct_http_candidates, direct_http_diag = direct_first_party_collect(source, aliases, cfg)
        diag["direct_http"] = direct_http_diag
        local_candidates.extend(direct_http_candidates)
        if direct_http_candidates:
            diag["mode"] = "direct_official_fast_path"
            diag["search"] = {"skipped": True, "reason": "direct first-party detail pages succeeded"}
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag
        # V44: when a public listing is login/JS gated (not authoritative), use
        # Tavily only to discover indexed official detail URLs. Search snippets
        # are never evidence; each official page is fetched and target-verified.
        indexed_candidates, indexed_diag = tavily_official_detail_discovery(source, aliases)
        diag["indexed_official"] = indexed_diag
        local_candidates.extend(indexed_candidates)
        if indexed_candidates:
            diag["mode"] = "indexed_official_fast_path"
            diag["search"] = {"skipped": True, "reason": "indexed official detail pages directly verified"}
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag

        # V45: a successful indexed-official discovery pass with no verified
        # target is a clean *technical* completion, not proof that the source
        # has no offer. This avoids turning an exhausted optional Firecrawl
        # fallback into a global degraded run after our public first-party
        # discovery strategy itself completed successfully. Adoption still
        # requires independent strict verified sources; no negative evidence is
        # created and absenceAuthoritative remains false. If any eligible detail
        # page failed direct verification, keep falling back/fail-degraded.
        indexed_detail_failed = any(x.get("ok") is False for x in (indexed_diag.get("details") or []))
        if indexed_diag.get("searchCompleted") and not indexed_detail_failed:
            diag["mode"] = "indexed_official_no_match"
            diag["search"] = {
                "skipped": True,
                "reason": "indexed public official-detail discovery completed with no verified target; absence not authoritative",
            }
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag

        if source.get("direct_listing_authoritative") and direct_http_diag.get("allListingsFetched"):
            diag["mode"] = "direct_clean_negative"
            diag["search"] = {"skipped": True, "reason": "authoritative first-party listings fetched cleanly with no target detail"}
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag

        if not key:
            diag["mode"] = "firecrawl_unavailable"
            diag["search"] = {"ok": False, "error": "FIRECRAWL_API_KEY unavailable after direct-first attempt"}
            diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
            return idx, local_candidates, diag

        direct = None
        try:
            direct = direct_scrape(key, source, aliases)
            diag["direct"] = {
                "ok": True,
                "targetFound": bool((direct.get("metadata") or {}).get("targetFound")),
                "markdownChars": len(direct.get("markdown") or ""),
                "links": len(direct.get("links") or []),
            }
            if diag["direct"]["targetFound"]:
                local_candidates.append(direct)
        except Exception as e:
            diag["direct"] = {"ok": False, "error": str(e)[:500]}

        if direct is not None:
            for ow_url in discover_offerwall_links(direct, cfg):
                host = (urlparse(ow_url).hostname or "").lower()
                try:
                    ow = scrape_offerwall(key, source, ow_url, aliases)
                    hit = bool((ow.get("metadata") or {}).get("targetFound"))
                    diag["offerwalls"].append({"domain": host, "ok": True, "targetFound": hit})
                    if hit:
                        local_candidates.append(ow)
                except Exception as e:
                    diag["offerwalls"].append({"domain": host, "ok": False, "error": str(e)[:300]})

            provider_links = discover_provider_hub_links(direct, source)
            diag["provider_hubs"] = []
            for provider_url in provider_links:
                host=(urlparse(provider_url).hostname or "").lower()
                try:
                    pc=scrape_provider_hub(key,source,provider_url,aliases)
                    hit=bool((pc.get("metadata") or {}).get("targetFound"))
                    diag["provider_hubs"].append({
                        "domain": host,
                        "safeUrl": sanitize_url(provider_url),
                        "ok": True,
                        "targetFound": hit,
                    })
                    if hit:
                        local_candidates.append(pc)
                except Exception as e:
                    diag["provider_hubs"].append({
                        "domain": host,
                        "safeUrl": sanitize_url(provider_url),
                        "ok": False,
                        "error": str(e)[:300],
                    })
        else:
            diag["provider_hubs"] = []

        try:
            found = domain_search(key, source, aliases)
            diag["search"] = {"ok": True, "townshipResults": len(found)}
            local_candidates.extend(found)
            known_urls = set(source.get("known_target_urls") or [])
            verified_hits, verified_diag = verify_search_hits(
                key, source, found, aliases, skip_urls=known_urls
            )
            diag["search_verified"] = verified_diag
            local_candidates.extend(verified_hits)
            already = known_urls | {c.get("url") for c in verified_hits if c.get("url")}
            followed, followed_diag = follow_candidate_links(
                key, source, found + verified_hits, aliases, cfg,
                limit=6, skip_urls=already
            )
            diag["followed_details"] = followed_diag
            local_candidates.extend(followed)
        except Exception as e:
            diag["search"] = {"ok": False, "error": str(e)[:500]}

        diag["elapsedSeconds"] = round(time.monotonic() - source_started, 1)
        return idx, local_candidates, diag

    priority = sorted(
        list(enumerate(sources)),
        key=lambda pair: (
            0 if not pair[1].get("prefer_known_pages", False) else 1,
            pair[0],
        ),
    )

    results = {}
    print(f"            並列取得: 最大{workers}サイト")
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="poigamelab-fc") as pool:
        future_map = {
            pool.submit(collect_one, idx, source): (idx, source)
            for idx, source in priority
        }
        for fut in as_completed(future_map):
            idx, source = future_map[fut]
            try:
                result_idx, local_candidates, diag = fut.result()
            except Exception as e:
                result_idx = idx
                local_candidates = []
                diag = {
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "mode": "failed",
                    "elapsedSeconds": None,
                    "fatalError": str(e)[:500],
                }
            results[result_idx] = (local_candidates, diag)
            sec = diag.get("elapsedSeconds")
            if diag.get("mode") in ("known_official_fast_path", "direct_official_fast_path"):
                print(f"      [{result_idx+1}/{len(sources)}] {source['name']} 公式ページ直行: {len(local_candidates)}件 / {sec}秒")
            elif diag.get("mode") == "direct_clean_negative":
                print(f"      [{result_idx+1}/{len(sources)}] {source['name']} 公式一覧確認: 対象なし / {sec}秒")
            elif diag.get("mode") == "indexed_official_no_match":
                print(f"      [{result_idx+1}/{len(sources)}] {source['name']} 公開公式詳細探索: 確認案件なし（不在断定なし） / {sec}秒")
            else:
                print(f"      [{result_idx+1}/{len(sources)}] {source['name']} 探索: {sec}秒")

    candidates = []
    diagnostics = []
    for idx in range(len(sources)):
        local_candidates, diag = results.get(idx, ([], {
            "source_id": sources[idx]["id"],
            "source_name": sources[idx]["name"],
            "mode": "missing_result",
        }))
        candidates.extend(local_candidates)
        diagnostics.append(diag)

    best = {}
    for c in candidates:
        key2 = (c.get("source_id"), offer_identity_url(c.get("url") or ""))
        old = best.get(key2)
        if old is None or candidate_priority(c) < candidate_priority(old):
            best[key2] = c
    return list(best.values()), diagnostics



def assess_collection_completeness(diagnostics):
    """Return (complete, reasons) without guessing whether a missing offer is truly gone.

    A clean complete run may replace the current game's snapshot. A degraded run
    may only merge fresh successes, preserving previously verified rows.
    """
    reasons = []
    for d in diagnostics or []:
        sid = d.get("source_id") or "unknown"
        if d.get("fatalError"):
            reasons.append(f"{sid}:fatal")
        search = d.get("search")
        if isinstance(search, dict) and search.get("ok") is False:
            reasons.append(f"{sid}:search_failed")
        if isinstance(search, dict) and search.get("partialAccepted") is True:
            reasons.append(f"{sid}:partial_known_fast_path")
        for kp in d.get("known_pages") or []:
            if kp.get("ok") is False:
                reasons.append(f"{sid}:known_page_{kp.get('cache') or 'failed'}")
    return (len(reasons) == 0), sorted(set(reasons))


def extract_interaction_text(res):
    texts = []
    for step in res.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                texts.append(item["text"])
    if not texts:
        raise RuntimeError("Geminiからテキスト応答を取得できませんでした。")
    return "\n".join(texts).strip()


def parse_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError("Gemini応答からJSONを取り出せませんでした。")
        return json.loads(m.group(0))


def gemini_call(key, model, prompt):
    res = post_json(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        {"model": model, "input": prompt, "store": False},
        headers={"x-goog-api-key": key},
        timeout=180,
    )
    return parse_json_text(extract_interaction_text(res))


def gemini_extract_batch(key, candidates):
    target_game = CURRENT_TARGET.get("game") or "対象ゲーム"
    aliases = CURRENT_TARGET.get("aliases") or [target_game]
    prompt = f"""あなたはPOIGAME LABの案件抽出・検証AIです。
以下はPOIGAME LABが登録したポイントサイトについて、Firecrawlが公式ページ・登録ドメイン検索から取得した「{target_game}」関連ページです。

厳守:
- 対象ゲームは「{target_game}」。別ゲームの金額を絶対に混ぜない。
- 対象表記: {", ".join(aliases)}
- ポイントサイト名、報酬額、達成条件、OS、案件URLを本文で裏付けられるものだけoffersへ入れる。
- 検索結果のtitle/descriptionだけで金額を確定せず、markdown本文を優先する。
- 同じサイトでもOS違い・報酬違い・案件URL違いは別offersとして必ず残す。
- 1候補内に複数案件があればすべて抽出する。
- 円換算が明確な場合のみreward_yenを整数にする。
- reward_yenが不明でも対象ゲーム案件ページ自体が明確なら候補として残してよい。
- 人間確認へ安易に回さず、不十分なものはpublishable=falseにする。
- JSON以外は出力禁止。

形式:
{{
  "game":{json.dumps(target_game, ensure_ascii=False)},
  "offers":[
    {{
      "site":"",
      "reward_yen":null,
      "condition":"",
      "platform":"",
      "deadline":"",
      "url":"",
      "evidence_urls":[],
      "confidence":0,
      "publishable":false,
      "reason":""
    }}
  ],
  "verdict":"",
  "needs_human_review":false
}}

Firecrawl取得結果:
""" + json.dumps(candidates, ensure_ascii=False)[:180000]

    configured = os.getenv("GEMINI_MODEL", "").strip()
    models = []
    for m in [configured, "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash"]:
        if m and m not in models:
            models.append(m)

    errors = []
    for model in models:
        for attempt, delay in enumerate((0, 5), start=1):
            if delay:
                time.sleep(delay)
            try:
                print(f"      Gemini: {model} を試行 ({attempt}/2)")
                return gemini_call(key, model, prompt), model
            except HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                errors.append(f"{model} HTTP {e.code}: {body[:220]}")
                if e.code == 429 or 500 <= e.code <= 599:
                    continue
                break
            except (URLError, TimeoutError) as e:
                errors.append(f"{model} network: {e}")
                continue
            except Exception as e:
                errors.append(f"{model}: {e}")
                break
    raise RuntimeError("Geminiの全候補モデルで検証できませんでした。\n" + "\n".join(errors[-8:]))


def host_matches_source(url, config):
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False, ""
    host = host.lower()
    for s in config["sources"]:
        for d in s.get("search_domains") or []:
            d = d.lower()
            if host == d or host.endswith("." + d):
                return True, s["id"]
    for d in config.get("offerwall_domains_discovered") or []:
        d = d.lower()
        if host == d or host.endswith("." + d):
            return True, "offerwall:" + d
    return False, ""



def candidate_priority(c):
    """Put strongest evidence first so official pages are never lost to prompt limits."""
    kind_score = {
        "direct_official_detail": 0,
        "known_official_probe": 1,
        "known_official_cache": 2,
        "followed_detail": 3,
        "official_search_verified": 4,
        "verified_search_hit": 4,
        "domain_search": 5,
        "direct": 5,
        "provider_hub_scrape": 6,
        "offerwall_scrape": 7,
    }
    return (kind_score.get(c.get("kind"), 9), -len(c.get("markdown") or ""))


def merge_offers(results):
    merged = {"game": CURRENT_TARGET.get("game") or "対象ゲーム", "offers": [], "verdict": "", "needs_human_review": False}
    seen = set()
    verdicts = []
    for result in results:
        if result.get("verdict"):
            verdicts.append(str(result["verdict"]))
        if result.get("needs_human_review"):
            merged["needs_human_review"] = True
        for offer in result.get("offers") or []:
            key = (str(offer.get("site") or "").strip().lower(), str(offer.get("url") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            merged["offers"].append(offer)
    merged["verdict"] = " / ".join(verdicts)[:2000]
    return merged


def gemini_extract(key, candidates):
    """Extract per registered source instead of one giant prompt.
    V5 could place COINCOME/chobirich after the 85k prompt cutoff. This guarantees
    every source gets its own extraction pass and prioritizes official evidence.
    """
    grouped = {}
    for c in candidates:
        grouped.setdefault(c.get("source_id") or "unknown", []).append(c)

    results = []
    used_models = []
    for source_id, items in grouped.items():
        items = sorted(items, key=candidate_priority)
        # Remove exact URL duplicates for the AI pass while keeping raw evidence on disk.
        unique = []
        seen = set()
        for c in items:
            k = c.get("url") or (c.get("kind"), c.get("title"))
            if k in seen:
                continue
            seen.add(k)
            unique.append(c)
        print(f"      Gemini抽出: {source_id} ({len(unique)}候補)")
        result, model = gemini_extract_batch(key, unique)
        results.append(result)
        used_models.append(model)

    return merge_offers(results), ",".join(dict.fromkeys(used_models))



def parse_int_amount(text):
    if text is None:
        return None
    m = re.search(r"([0-9][0-9,]{1,})", str(text))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def same_offer_identity(a, b):
    """Evidence must identify the same public offer, not merely the same site."""
    if not a or not b:
        return False
    return offer_identity_url(a) == offer_identity_url(b)

def deterministic_amount_from_text(site, text):
    text = text or ""
    if site == "ワラウ":
        patterns = [
            r"累計(?:最大)?\s*([0-9][0-9,]*)\s*pt",
            r"最大\s*([0-9][0-9,]*)\s*pt",
            r"([0-9][0-9,]*)\s*pt\s*[（(]?\s*1\s*pt\s*=\s*1\s*円",
        ]
    else:
        patterns = [
            r"最大\s*([0-9][0-9,]*)\s*円(?:相当)?",
            r"([0-9][0-9,]*)\s*円(?:相当)?",
        ]
    values=[]
    for pat in patterns:
        for m in re.finditer(pat,text,flags=re.I):
            try:
                v=int(m.group(1).replace(",",""))
                if 0 < v < 1_000_000:
                    values.append(v)
            except Exception:
                pass
    return max(values) if values else None

def infer_reward_yen_from_offer(offer, candidates):
    """Infer/cross-check reward using ONLY exact same-offer identity evidence."""
    site=str(offer.get("site") or "")
    url=str(offer.get("url") or "")
    evidence_text="\n".join([str(offer.get("condition") or ""),str(offer.get("reason") or "")])

    exact=[]
    for c in candidates:
        if url and c.get("url") and same_offer_identity(url,c.get("url")):
            exact.append(c)
            evidence_text += "\n" + str(c.get("markdown") or "")

    deterministic=deterministic_amount_from_text("ワラウ" if (site=="ワラウ" or "warau.jp" in url) else site,evidence_text)
    gemini=offer.get("reward_yen")
    if deterministic:
        return deterministic, ("python_warau_same_identity" if (site=="ワラウ" or "warau.jp" in url) else "python_same_identity_explicit_yen"), exact
    if isinstance(gemini,(int,float)) and 0 < gemini < 1_000_000:
        return int(gemini),"gemini",exact
    return None,"unresolved",exact

def apply_deterministic_enrichment(verified, candidates, cfg):
    """Python owns normalization + strict same-offer publication gate."""
    for offer in verified.get("offers", []):
        recognized, source_id = host_matches_source(offer.get("url") or "", cfg)
        first_party_source = bool(source_id) and not str(source_id).startswith("offerwall:")
        offer["registered_source"] = source_id or None

        evidence_urls=[u for u in (offer.get("evidence_urls") or []) if u]
        evidence_sources=[host_matches_source(u,cfg)[1] for u in evidence_urls]
        evidence_hosts_ok=bool(evidence_urls) and first_party_source and all(x==source_id for x in evidence_sources)

        # Critical V20 rule: every cited evidence URL must be the SAME offer identity.
        evidence_identity_ok=bool(evidence_urls) and bool(offer.get("url")) and all(
            same_offer_identity(offer.get("url"),u) for u in evidence_urls
        )

        inferred,reward_source,exact_candidates=infer_reward_yen_from_offer(offer,candidates)
        original=offer.get("reward_yen")
        if inferred is not None:
            offer["reward_yen"]=inferred
        offer["reward_source"]=reward_source

        # If exact-identity deterministic text states an amount, it is authoritative.
        # Otherwise Gemini amount is acceptable only when exact identity evidence exists.
        deterministic_found=reward_source.startswith("python_")
        reward_consistent = bool(exact_candidates) and (
            deterministic_found or (isinstance(original,(int,float)) and original>0)
        )

        reward=offer.get("reward_yen")
        reward_ok=isinstance(reward,(int,float)) and 0 < reward < 1_000_000
        condition_ok=len(str(offer.get("condition") or "").strip()) >= 8
        checks={
            "registered_domain":recognized,
            "first_party_registered_source":first_party_source,
            "url_present":bool(offer.get("url")),
            "evidence_present":bool(evidence_urls),
            "evidence_domains_registered":evidence_hosts_ok,
            "evidence_same_offer_identity":evidence_identity_ok,
            "exact_identity_candidate_present":bool(exact_candidates),
            "reward_valid":reward_ok,
            "reward_consistent":reward_consistent,
            "condition_present":condition_ok,
        }
        offer["deterministic_checks"]=checks
        offer["auto_publish_ready"]=all(checks.values())
    return verified

def main():
    total_started = time.monotonic()
    load_dotenv()
    fc = os.getenv("FIRECRAWL_API_KEY", "").strip()
    gem = os.getenv("GEMINI_API_KEY", "").strip()
    missing = [n for n, v in [("GEMINI_API_KEY", gem)] if not v]
    if missing:
        print("ERROR: .env に " + ", ".join(missing) + " がありません。", file=sys.stderr)
        return 2

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    global CURRENT_TARGET
    CURRENT_TARGET = cfg.get("target") or CURRENT_TARGET
    configure_output_paths(cfg)
    target_game = CURRENT_TARGET.get("game") or "対象ゲーム"
    print(f"[1/4] {target_game}: 公式サイト直接取得を優先して登録済みポイントサイトを調査中…")
    candidates, diagnostics = collect_firecrawl(fc, cfg)

    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUT.write_text(json.dumps({
        "phase": "PHASE2_AUTO_REFRESH_V23",
        "runAt": now_iso(),
        "target": cfg["target"],
        "diagnostics": diagnostics,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "privacy": "個人識別子付きOfferwall URLは保存していません。",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[2/4] {target_game}候補を整理: {len(candidates)}件")
    if not candidates:
        OUT.write_text(json.dumps({
            "phase": "PHASE2_AUTO_REFRESH_V23",
            "runAt": now_iso(),
            "status": "no_township_candidates",
            "diagnostics": diagnostics,
            "candidateFile": str(RAW_OUT.relative_to(ROOT)),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[3/4] Geminiへ渡せる{target_game}本文が0件のためスキップ")
        print("[4/4] 診断結果を保存しました")
        print(f"      候補: {RAW_OUT.relative_to(ROOT)}")
        print(f"      結果: {OUT.relative_to(ROOT)}")
        return 4

    print("[3/4] Geminiで案件情報を抽出・照合中…")
    try:
        verified, used_model = gemini_extract(gem, candidates)
    except Exception as e:
        OUT.write_text(json.dumps({
            "phase": "PHASE2_AUTO_REFRESH_V23",
            "runAt": now_iso(),
            "status": "gemini_unavailable",
            "candidateCount": len(candidates),
            "candidateFile": str(RAW_OUT.relative_to(ROOT)),
            "error": str(e),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[4/4] Firecrawl収集結果は保存済み。Geminiは今回は利用できませんでした。")
        print(f"      候補: {RAW_OUT.relative_to(ROOT)}")
        print(f"      診断: {OUT.relative_to(ROOT)}")
        return 3

    # Geminiは読む係。正規化・補完・掲載判定はPython側で再現可能に処理。
    verified = apply_deterministic_enrichment(verified, candidates, cfg)

    ready = sum(1 for o in verified.get("offers", []) if o.get("auto_publish_ready"))
    collection_complete, degraded_reasons = assess_collection_completeness(diagnostics)
    output = {
        "phase": "PHASE2_AUTO_REFRESH_V23",
        "runAt": now_iso(),
        "collector": "Phase3 Research V38: direct-first first-party research + Firecrawl best-effort fallback + strict verifier",
        "candidateCount": len(candidates),
        "geminiModel": used_model,
        "verified": verified,
        "diagnostics": diagnostics,
        "health": {
            "publishableCount": ready,
            "collectionComplete": collection_complete,
            "degradedReasons": degraded_reasons,
            "publishableBySource": {
                sid: sum(1 for o in verified.get("offers", []) if o.get("auto_publish_ready") and o.get("registered_source") == sid)
                for sid in [x.get("id") for x in cfg.get("sources", [])]
            },
            "exceptionCount": sum(1 for o in verified.get("offers", []) if not o.get("auto_publish_ready")),
        },
        "policy": {
            "autoPublish": "Python deterministic gate only: same first-party registered source URL/evidence + valid reward + condition",
            "offerwalls": "親サイトから自動発見。個人識別子付きURLは実行中だけ使用し、保存時はqueryを除去",
        },
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # PHASE 1 Publisher: deterministic gateを通った案件だけサイト用データへ。
    # V28 research bridge uses quarantine mode: verify fully, but never publish.
    publish_mode = os.getenv("POIGAMELAB_PUBLISH_MODE", "publish").strip().lower()
    if publish_mode == "quarantine":
        published_rows = []
        exception_rows = [o for o in verified.get("offers", []) if not o.get("auto_publish_ready")]
        output["policy"]["publishMode"] = "quarantine"
        OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[Publisher] research quarantine: published_offers.csv は変更しません")
    else:
        try:
            from publish_verified_offers import publish
            published_rows, exception_rows = publish(OUT)
        except Exception as e:
            print(f"[Publisher] ERROR: {e}", file=sys.stderr)
            return 5

    print("[4/4] 完了")
    print(f"      収集候補: {len(candidates)}件")
    print(f"      AI抽出: {len(verified.get('offers', []))}件")
    cache_hits = sum(
        1 for d in diagnostics for x in (d.get("known_pages") or [])
        if x.get("cache") == "hit"
    )
    cache_misses = sum(
        1 for d in diagnostics for x in (d.get("known_pages") or [])
        if x.get("cache") == "miss"
    )
    print(f"      自動掲載可能: {ready}件")
    print(f"      掲載データ生成: {len(published_rows)}件")
    print(f"      例外キュー: {len(exception_rows)}件")
    print(f"      公式ページキャッシュ: HIT {cache_hits} / MISS {cache_misses}")
    print(f"      結果: {OUT.relative_to(ROOT)}")
    print(f"      合計時間: {round(time.monotonic() - total_started, 1)}秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
