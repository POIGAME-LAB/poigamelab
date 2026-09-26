#!/usr/bin/env python3
"""Shortcuts-friendly Point Income catalog capture for locked automation.

This light mode intentionally captures only the current public category-68
listing and dispatches it to GitHub. It skips detail pages and remote alias
downloads so it can finish within the tighter Shortcuts/Pythonista extension
budget. GitHub may refresh rewards only for already-verified exact offer IDs.
New/changed offers remain candidate-only until a full reviewed detail capture.
"""
import base64
import gzip
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://sp.pointi.jp"
SOURCE_URL = BASE + "/list.php?cat_no=68"
LISTING_TEMPLATE = BASE + "/ajax_load/load_list_site.php?page={page}&cat_no=68&od=1"
GITHUB_API = (
    "https://api.github.com/repos/POIGAME-LAB/poigamelab/"
    "actions/workflows/import-point-income-device-catalog.yml/dispatches"
)
KEYCHAIN_SERVICE = "POIGAMELAB"
KEYCHAIN_ACCOUNT = "github_actions_dispatch_token"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_RE = re.compile(r"^/ad/(\d+)/?$")
POINT_RE = re.compile(r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt", re.I)
TOKEN_RE = re.compile(r"^(?:github_pat_|ghp_)[A-Za-z0-9_]+$")
MAX_PAGES = 40
BATCH_SIZE = 8
MAX_WORKERS = 8
MAX_PAGE_BYTES = 120_000
MAX_DISPATCH_CHARS = 60_000


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
            self.links.append((self.href, text))
            self.href = None
            self.parts = []


def first_party(url):
    try:
        p = urlparse(str(url or ""))
    except Exception:
        return False
    return p.scheme == "https" and (p.hostname or "").lower() in ALLOWED_HOSTS


def platform_from_title(title):
    ios = bool(re.search(r"(?:iOS|iPhone)\s*用", title, re.I))
    android = bool(re.search(r"Android\s*用", title, re.I))
    if ios and not android:
        return "iOS"
    if android and not ios:
        return "Android"
    if ios and android:
        return "iOS|Android"
    return ""


def clean_title(text):
    m = POINT_RE.search(text)
    title = text[:m.start()].strip() if m else text.strip()
    title = re.sub(r"\s+[0-9][0-9,]*円\(税込\)の商品ご購入で$", "", title)
    return title[:260].strip()


def fetch_page(page):
    url = LISTING_TEMPLATE.format(page=page)
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.5",
        "Referer": SOURCE_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "close",
    })
    with urlopen(req, timeout=12) as r:
        raw = r.read(MAX_PAGE_BYTES + 1)
        final = r.geturl()
    if len(raw) > MAX_PAGE_BYTES:
        raise RuntimeError("page_too_large")
    if not first_party(final):
        raise RuntimeError("unexpected_redirect")
    text = raw.decode("utf-8", "replace")
    if (
        "このページはお住まいの地域からご利用になれません" in text
        or "information.php?cn=2&sn=1" in final
    ):
        raise RuntimeError("geo_gate")
    parser = LinkParser()
    parser.feed(text)
    offers = []
    seen = set()
    for href, anchor in parser.links:
        absolute = urljoin(final, unescape(str(href or ""))).split("#", 1)[0]
        if not first_party(absolute):
            continue
        p = urlparse(absolute)
        m = AD_RE.fullmatch(p.path or "")
        if not m or p.query:
            continue
        ad_id = m.group(1)
        if ad_id in seen:
            continue
        vals = [int(x.replace(",", "")) for x in POINT_RE.findall(anchor)]
        if not vals:
            continue
        points = vals[-1]
        title = clean_title(anchor)
        if not title or not 0 < points <= 10_000_000:
            continue
        seen.add(ad_id)
        offers.append({
            "adId": ad_id,
            "url": f"{BASE}/ad/{ad_id}/",
            "title": title,
            "platform": platform_from_title(title),
            "currentPoints": points,
            "currentYen": points / 10,
            "rewardText": f"{points:,}pt",
        })
    return page, offers


def capture():
    pages = []
    all_offers = []
    seen = set()
    stopped = "max_pages"

    for batch_start in range(1, MAX_PAGES + 1, BATCH_SIZE):
        batch = list(range(batch_start, min(MAX_PAGES, batch_start + BATCH_SIZE - 1) + 1))
        results = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(fetch_page, page): page for page in batch}
            for fut in as_completed(futures):
                page = futures[fut]
                try:
                    _, offers = fut.result()
                except Exception as exc:
                    raise SystemExit(f"Point Income取得失敗 page={page}: {exc}")
                results[page] = offers

        for page in batch:
            offers = results[page]
            pages.append({"page": page, "offerCount": len(offers)})
            if not offers:
                stopped = "empty_page"
                return build_payload(all_offers, pages, stopped)
            for offer in offers:
                if offer["adId"] not in seen:
                    seen.add(offer["adId"])
                    all_offers.append(offer)

    return build_payload(all_offers, pages, stopped)


def build_payload(offers, pages, stopped):
    if not offers:
        raise SystemExit("Point Income案件を取得できませんでした。")
    return {
        "schemaVersion": 2,
        "source": "point_income",
        "sourceUrl": SOURCE_URL,
        "listingEndpoint": "/ajax_load/load_list_site.php",
        "category": 68,
        "order": 1,
        "pointRate": "10pt=1JPY",
        "pageCount": len(pages),
        "pages": pages,
        "stoppedBecause": stopped,
        "candidateOnly": True,
        "catalogCompleteClaim": False,
        "offers": offers,
        "count": len(offers),
    }


def stored_token():
    try:
        import keychain
        token = str(keychain.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT) or "").strip()
    except Exception:
        return ""
    if 30 <= len(token) <= 255 and TOKEN_RE.fullmatch(token):
        return token
    return ""


def encode(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = gzip.compress(raw, compresslevel=7, mtime=0)
    encoded = base64.b64encode(packed).decode("ascii")
    if len(encoded) > MAX_DISPATCH_CHARS:
        raise SystemExit("送信データが大きすぎます。")
    return encoded


def dispatch(encoded, token):
    body = json.dumps({
        "ref": "main",
        "inputs": {"point_income_catalog_base64": encoded},
    }, separators=(",", ":")).encode("utf-8")
    req = Request(GITHUB_API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "POIGAMELAB-PointIncome-iPhone-Light/1.0",
        "Connection": "close",
    })
    try:
        with urlopen(req, timeout=15) as r:
            status = getattr(r, "status", 200)
            r.read()
    except HTTPError as exc:
        raise SystemExit(f"GitHub送信失敗 HTTP {exc.code}")
    except URLError as exc:
        raise SystemExit("GitHub接続失敗: " + str(exc.reason))
    if status not in {200, 204}:
        raise SystemExit(f"GitHub送信未完了 HTTP {status}")


def main():
    token = stored_token()
    if not token:
        raise SystemExit(
            "GitHubトークンがKeychainにありません。"
            "通常版 point_income_one_tap_v2.py を一度Pythonista本体で実行してください。"
        )
    payload = capture()
    encoded = encode(payload)
    dispatch(encoded, token)
    print(json.dumps({
        "ok": True,
        "count": payload["count"],
        "pageCount": payload["pageCount"],
        "mode": "shortcuts_light",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
