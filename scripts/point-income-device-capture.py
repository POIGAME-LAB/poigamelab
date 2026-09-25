#!/usr/bin/env python3
"""Capture the current public Point Income category-68 catalog on an iPhone.

Point Income geo-gates cloud CI, so this is intentionally designed for a
Japan-residential iPhone/Pythonista run. It transmits only public offer fields:
ad id/url, title, platform and displayed current points. No HTML, cookies,
credentials or account state are emitted.
"""
import base64
import json
import re
import time
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor

BASE = "https://sp.pointi.jp"
START_URL = BASE + "/list.php?cat_no=68"
LISTING_TEMPLATE = BASE + "/ajax_load/load_list_site.php?page={page}&cat_no=68&od=1"
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_RE = re.compile(r"^/ad/(\\d+)/?$")
POINT_RE = re.compile(r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\\s*pt", re.I)
MAX_PAGES = 50
MAX_BYTES = 5_000_000

jar = CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\\s+", " ", " ".join(self._text)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def first_party(url):
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in ALLOWED_HOSTS


def fetch(url, ajax=False):
    if not first_party(url):
        raise SystemExit("Point Income の https URL 以外は取得しません。")
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.5",
        "Referer": START_URL,
    }
    if ajax:
        headers.update({
            "Accept": "text/html, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        })
    else:
        headers["Accept"] = "text/html,application/xhtml+xml"

    request = Request(url, headers=headers)
    with opener.open(request, timeout=25) as response:
        data = response.read(MAX_BYTES + 1)
        final = response.geturl()

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


def platform_from_title(title):
    has_ios = bool(re.search(r"(?:iOS|iPhone)\\s*用", title, re.I))
    has_android = bool(re.search(r"Android\\s*用", title, re.I))
    if has_ios and has_android:
        return "iOS|Android"
    if has_ios:
        return "iOS"
    if has_android:
        return "Android"
    return ""


def clean_title(text):
    match = POINT_RE.search(text)
    title = text[:match.start()].strip() if match else text.strip()
    title = re.sub(r"\\s+[0-9][0-9,]*円\\(税込\\)の商品ご購入で$", "", title)
    return title[:260].strip()


def parse_listing_page(raw, final_url):
    parser = LinkParser()
    parser.feed(raw)
    offers = []
    seen = set()
    for href, text in parser.links:
        absolute = urljoin(final_url, unescape(str(href or ""))).split("#", 1)[0]
        if not first_party(absolute):
            continue
        parsed = urlparse(absolute)
        match = AD_RE.fullmatch(parsed.path or "")
        if not match or parsed.query:
            continue
        ad_id = match.group(1)
        if ad_id in seen:
            continue
        points = [
            int(value.replace(",", ""))
            for value in POINT_RE.findall(text)
        ]
        if not points:
            continue
        current_points = points[-1]
        if not 0 < current_points <= 10_000_000:
            continue
        title = clean_title(text)
        if not 2 <= len(title) <= 260:
            continue
        seen.add(ad_id)
        offers.append({
            "adId": ad_id,
            "url": f"{BASE}/ad/{ad_id}/",
            "title": title,
            "platform": platform_from_title(title),
            "currentPoints": current_points,
            "currentYen": current_points / 10,
            "rewardText": f"{current_points:,}pt",
        })
    return offers


def capture():
    fetch(START_URL, ajax=False)
    all_offers = []
    seen = set()
    pages = []
    previous_signature = None
    stopped_because = "max_pages"

    for page in range(1, MAX_PAGES + 1):
        url = LISTING_TEMPLATE.format(page=page)
        raw, final = fetch(url, ajax=True)
        offers = parse_listing_page(raw, final)
        signature = tuple(item["adId"] for item in offers)
        pages.append({"page": page, "offerCount": len(offers)})

        if not offers:
            stopped_because = "empty_page"
            break
        if signature == previous_signature:
            stopped_because = "repeated_page"
            break
        previous_signature = signature

        for offer in offers:
            if offer["adId"] not in seen:
                seen.add(offer["adId"])
                all_offers.append(offer)

        time.sleep(0.12)

    if not all_offers:
        raise SystemExit("案件を1件も取得できなかったため停止しました。")

    return {
        "schemaVersion": 2,
        "source": "point_income",
        "sourceUrl": START_URL,
        "listingEndpoint": "/ajax_load/load_list_site.php",
        "category": 68,
        "order": 1,
        "pointRate": "10pt=1JPY",
        "pageCount": len(pages),
        "pages": pages,
        "stoppedBecause": stopped_because,
        "candidateOnly": True,
        "catalogCompleteClaim": False,
        "offers": all_offers,
        "count": len(all_offers),
    }


def main():
    payload = capture()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.b64encode(raw).decode("ascii")
    print("POINT_INCOME_CATALOG_V2")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\nPOINT_INCOME_BASE64")
    print(encoded)
    print("\n※ HTML・Cookie・ログイン情報は出力していません。")


if __name__ == "__main__":
    main()
