#!/usr/bin/env python3
"""Capture public Point Income offer identities from a Japan-residential iPhone.

Designed for Pythonista/iPhone and standard Python. It never sends cookies,
credentials, or HTML. It prints candidate-only public /ad/<id>/ identities.
"""
import base64
import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)
MAX_PAGES = 30
MAX_BYTES = 5_000_000
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_RE = re.compile(r"^/ad/(\d+)/?$")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.next_links = []
        self._href = None
        self._rel = ""
        self._text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self._href = a.get("href")
            self._rel = a.get("rel", "")
            self._text = []
        elif tag == "link":
            rel = str(a.get("rel") or "").lower()
            href = a.get("href")
            if href and "next" in rel.split():
                self.next_links.append(href)

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or self._href is None:
            return
        text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
        self.links.append((self._href, text, self._rel))
        if "next" in str(self._rel or "").lower().split():
            self.next_links.append(self._href)
        elif text in {"次へ", "次のページ", "次", "›", "»", ">"} or "次へ" in text:
            self.next_links.append(self._href)
        self._href = None
        self._rel = ""
        self._text = []


def first_party(url):
    try:
        p = urlparse(str(url or ""))
    except Exception:
        return False
    return p.scheme == "https" and (p.hostname or "").lower() in ALLOWED_HOSTS


def fetch(url):
    if not first_party(url):
        raise SystemExit("Point Income の https URL だけ指定してください。")
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.5",
    })
    with urlopen(req, timeout=25) as r:
        data = r.read(MAX_BYTES + 1)
        final = r.geturl()
        if len(data) > MAX_BYTES:
            raise SystemExit("ページが大きすぎるため停止しました。")
    raw = data.decode("utf-8", "replace")
    if (
        "このページはお住まいの地域からご利用になれません" in raw
        or "information.php?cn=2&sn=1" in final
    ):
        raise SystemExit(
            "Point Income の国内アクセス制御ページに転送されました。"
            " Wi-Fi/VPNを切り替え、通常の国内回線で再実行してください。"
        )
    return raw, final


def parse_page(raw, final_url):
    parser = PageParser()
    parser.feed(raw)
    ids = []
    seen = set()
    for href, _, _ in parser.links:
        absolute = urljoin(final_url, unescape(str(href or ""))).split("#", 1)[0]
        if not first_party(absolute):
            continue
        p = urlparse(absolute)
        m = AD_RE.fullmatch(p.path or "")
        if m and not p.query:
            ad_id = m.group(1)
            if ad_id not in seen:
                seen.add(ad_id)
                ids.append(ad_id)

    next_urls = []
    for href in parser.next_links:
        absolute = urljoin(final_url, unescape(str(href or ""))).split("#", 1)[0]
        if first_party(absolute) and absolute not in next_urls:
            next_urls.append(absolute)
    return ids, next_urls


def capture(start_url):
    queue = [start_url]
    visited = set()
    ids = []
    seen_ids = set()
    pages = []

    while queue and len(visited) < MAX_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        raw, final = fetch(url)
        page_ids, next_urls = parse_page(raw, final)
        for ad_id in page_ids:
            if ad_id not in seen_ids:
                seen_ids.add(ad_id)
                ids.append(ad_id)
        pages.append({
            "url": final,
            "adCount": len(page_ids),
        })
        for nxt in next_urls:
            if nxt not in visited and nxt not in queue:
                queue.append(nxt)

    if not ids:
        raise SystemExit(
            "このページから /ad/<数字>/ の案件URLを見つけられませんでした。"
            " Point Incomeのアプリ/ゲーム案件一覧ページURLを指定してください。"
        )

    payload = {
        "schemaVersion": 1,
        "source": "point_income",
        "sourceUrl": start_url,
        "pageCount": len(pages),
        "candidateOnly": True,
        "catalogCompleteClaim": False,
        "adIds": ids,
        "count": len(ids),
    }
    return payload


def main():
    start_url = sys.argv[1].strip() if len(sys.argv) > 1 else input(
        "Point Incomeのアプリ/ゲーム案件一覧URLを貼ってください: "
    ).strip()
    payload = capture(start_url)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    print("\nPOINT_INCOME_JSON")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\nPOINT_INCOME_BASE64")
    print(encoded)
    print("\n※ HTML・Cookie・ログイン情報は出力していません。")


if __name__ == "__main__":
    main()
