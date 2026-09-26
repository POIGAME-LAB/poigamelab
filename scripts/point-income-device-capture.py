#!/usr/bin/env python3
"""Capture Point Income category 68 on an iPhone and hand it to POIGAME LAB.

Point Income geo-gates cloud CI, so public offer discovery is performed from a
Japan-residential iPhone/Pythonista session. After one-time GitHub token setup,
a normal run is one tap: capture -> gzip/base64 -> GitHub Actions dispatch.

Only public offer fields are transmitted. Raw HTML, cookies, credentials,
account state and the GitHub token are never included in the payload.
"""
import base64
import gzip
import json
import re
import sys
import time
import unicodedata
from html import unescape
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, urlopen

BASE = "https://sp.pointi.jp"
START_URL = BASE + "/list.php?cat_no=68"
LISTING_TEMPLATE = BASE + "/ajax_load/load_list_site.php?page={page}&cat_no=68&od=1"
GITHUB_REPOSITORY = "POIGAME-LAB/poigamelab"
GITHUB_WORKFLOW = "import-point-income-device-catalog.yml"
GITHUB_API = (
    "https://api.github.com/repos/"
    + GITHUB_REPOSITORY
    + "/actions/workflows/"
    + GITHUB_WORKFLOW
    + "/dispatches"
)
KEYCHAIN_SERVICE = "POIGAMELAB"
KEYCHAIN_ACCOUNT = "github_actions_dispatch_token"
TARGET_CONFIG_URL = (
    "https://raw.githubusercontent.com/POIGAME-LAB/poigamelab/main/"
    "config/point_income_game_aliases.json"
)
TARGET_CONFIG_HOST = "raw.githubusercontent.com"
MAX_DETAIL_OFFERS = 40
MAX_DETAIL_SNIPPETS = 4
MAX_DETAIL_SNIPPET_CHARS = 1800
MAX_DETAIL_LEAD_CHARS = 2400
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}
AD_RE = re.compile(r"^/ad/(\d+)/?$")
POINT_RE = re.compile(r"([1-9][0-9]{0,2}(?:,[0-9]{3})*|[1-9][0-9]*)\s*pt", re.I)
MAX_PAGES = 50
MAX_BYTES = 5_000_000
MAX_DISPATCH_CHARS = 60_000
GITHUB_TOKEN_RE = re.compile(r"^(?:github_pat_|ghp_)[A-Za-z0-9_]+$")
MIN_GITHUB_TOKEN_LEN = 30
MAX_GITHUB_TOKEN_LEN = 255

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
            text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []



class PublicDetailParser(HTMLParser):
    """Extract only public visible text/metadata from an anonymous detail page."""

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.in_title = False
        self.heading_tag = ""
        self.heading_parts = []
        self.title_parts = []
        self.text_parts = []
        self.headings = []
        self.canonical = ""
        self.meta_description = ""

    def handle_starttag(self, tag, attrs):
        tag = (tag or "").lower()
        attrs_map = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "h3"}:
            self.heading_tag = tag
            self.heading_parts = []
        if tag == "link":
            rel = {x.casefold() for x in attrs_map.get("rel", "").split()}
            if "canonical" in rel and not self.canonical:
                self.canonical = attrs_map.get("href", "").strip()
        if tag == "meta":
            if attrs_map.get("name", "").casefold() == "description" and not self.meta_description:
                self.meta_description = attrs_map.get("content", "").strip()
        if tag in {"br", "p", "div", "li", "section", "article", "dt", "dd"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag):
        tag = (tag or "").lower()
        if tag in self.SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
        if tag == self.heading_tag:
            value = normalize_space(" ".join(self.heading_parts))
            if value and value not in self.headings:
                self.headings.append(value[:240])
            self.heading_tag = ""
            self.heading_parts = []
        if tag in {"p", "div", "li", "section", "article", "dt", "dd"}:
            self.text_parts.append(" ")

    def handle_data(self, data):
        if self.skip_depth:
            return
        value = str(data or "")
        self.text_parts.append(value)
        if self.in_title:
            self.title_parts.append(value)
        if self.heading_tag:
            self.heading_parts.append(value)


def normalize_space(value):
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def normalized_game_key(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for pattern in (
        r"【[^】]*】",
        r"\[[^\]]*\]",
        r"（(?:iOS|Android|iPhone)用）",
        r"\((?:iOS|Android|iPhone)用\)",
    ):
        text = re.sub(pattern, " ", text, flags=re.I)
    text = text.replace("＆", "&")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[・･·／/｜|：:‐-‒–—―_\-]+", "", text)
    text = re.sub(r"[【】\[\]（）()「」『』〈〉《》]", "", text)
    return text[:320]


FALLBACK_TARGETS = [
    {"game": "Township", "aliases": ["Township", "タウンシップ"]},
    {"game": "きのこ伝説", "aliases": ["きのこ伝説"]},
    {"game": "メメントモリ", "aliases": ["メメントモリ", "MementoMori", "Memento Mori"]},
    {"game": "ワーキングヒーロー", "aliases": ["ワーキングヒーロー", "Working Hero"]},
    {"game": "ホワイトアウト・サバイバル", "aliases": ["ホワイトアウト・サバイバル", "Whiteout Survival"]},
    {"game": "東京ディバンカー", "aliases": ["東京ディバンカー", "Tokyo Debunker"]},
    {"game": "パズル＆サバイバル", "aliases": ["パズル＆サバイバル", "パズル&サバイバル", "Puzzles & Survival", "Puzzles and Survival"]},
    {"game": "キングショット", "aliases": ["キングショット", "Kingshot"]},
    {"game": "放置少女", "aliases": ["放置少女"]},
    {"game": "エバーテイル", "aliases": ["エバーテイル", "Evertale"]},
    {"game": "ATLAS: EARTH", "aliases": ["ATLAS: EARTH", "ATLAS:EARTH", "ATLAS EARTH"]},
    {"game": "ファミリーファームの冒険", "aliases": ["ファミリーファームの冒険", "Family Farm Adventure"]},
    {"game": "クロンダイクの冒険", "aliases": ["クロンダイクの冒険", "Klondike Adventures"]},
    {"game": "Merge Help: ホームデザインパズル", "aliases": ["Merge Help", "ホームデザインパズル"]},
    {"game": "マジックジグソーパズル", "aliases": ["マジックジグソーパズル", "Magic Jigsaw Puzzles"]},
    {"game": "Sea Block 1010", "aliases": ["Sea Block 1010"]},
    {"game": "さる山温泉旅館", "aliases": ["さる山温泉旅館"]},
    {"game": "インポッシブルカート", "aliases": ["インポッシブルカート", "Impossible Cart"]},
    {"game": "天地英雄伝", "aliases": ["天地英雄伝"]},
    {"game": "High Roller Vegas", "aliases": ["High Roller Vegas", "ハイローラーベガス"]},
]


def validate_target_config(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        return []
    rows = data.get("games")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        return []
    out = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return []
        game = str(row.get("game") or "").strip()
        aliases = row.get("aliases")
        if not 1 <= len(game) <= 120 or not isinstance(aliases, list):
            return []
        cleaned = []
        for alias in aliases:
            alias = str(alias or "").strip()
            if not 1 <= len(alias) <= 120:
                return []
            if alias not in cleaned:
                cleaned.append(alias)
        if not cleaned or game in seen:
            return []
        seen.add(game)
        out.append({"game": game, "aliases": cleaned})
    return out


def load_target_config(open_url=urlopen):
    request = Request(
        TARGET_CONFIG_URL,
        headers={
            "User-Agent": "POIGAMELAB-PointIncome-iPhone/1.1",
            "Accept": "application/json",
        },
    )
    try:
        with open_url(request, timeout=15) as response:
            final = response.geturl() if hasattr(response, "geturl") else TARGET_CONFIG_URL
            parsed = urlparse(final)
            if parsed.scheme != "https" or (parsed.hostname or "").lower() != TARGET_CONFIG_HOST:
                return list(FALLBACK_TARGETS)
            raw = response.read(40_001)
        if len(raw) > 40_000:
            return list(FALLBACK_TARGETS)
        value = validate_target_config(json.loads(raw.decode("utf-8")))
        return value or list(FALLBACK_TARGETS)
    except Exception:
        return list(FALLBACK_TARGETS)


def match_target_game(title, targets):
    key = normalized_game_key(title)
    hits = []
    for row in targets:
        aliases = [
            normalized_game_key(alias)
            for alias in row.get("aliases", [])
            if str(alias or "").strip()
        ]
        if any(alias and alias in key for alias in aliases):
            hits.append(row["game"])
    return hits[0] if len(hits) == 1 else ""


def detail_keyword_snippets(text):
    markers = (
        "ポイント獲得条件",
        "獲得条件",
        "成果条件",
        "獲得対象外",
        "対象外",
        "注意事項",
        "お問い合わせ",
        "承認期間",
    )
    spans = []
    for marker in markers:
        start = 0
        while True:
            pos = text.find(marker, start)
            if pos < 0:
                break
            left = max(0, pos - 250)
            right = min(len(text), pos + MAX_DETAIL_SNIPPET_CHARS - 250)
            if not any(not (right <= a or left >= b) for a, b in spans):
                spans.append((left, right))
            start = pos + len(marker)
            if len(spans) >= MAX_DETAIL_SNIPPETS:
                break
        if len(spans) >= MAX_DETAIL_SNIPPETS:
            break
    return [text[a:b] for a, b in spans[:MAX_DETAIL_SNIPPETS]]


def parse_public_detail_evidence(raw, requested_url, final_url, offer, game):
    requested = urlparse(requested_url)
    final = urlparse(final_url)
    requested_match = AD_RE.fullmatch(requested.path or "")
    final_match = AD_RE.fullmatch(final.path or "")
    if (
        not requested_match
        or not final_match
        or requested_match.group(1) != final_match.group(1)
        or not first_party(final_url)
    ):
        raise ValueError("detail_identity_mismatch")

    parser = PublicDetailParser()
    parser.feed(raw)
    text = normalize_space(" ".join(parser.text_parts))
    canonical = urljoin(final_url, parser.canonical) if parser.canonical else ""
    if canonical:
        canonical_parsed = urlparse(canonical)
        canonical_match = AD_RE.fullmatch(canonical_parsed.path or "")
        if (
            not first_party(canonical)
            or not canonical_match
            or canonical_match.group(1) != requested_match.group(1)
        ):
            canonical = ""

    return {
        "evidenceVersion": 1,
        "adId": requested_match.group(1),
        "gameHint": game,
        "url": requested_url,
        "finalUrl": final_url,
        "canonicalUrl": canonical,
        "listingTitle": str(offer.get("title") or "")[:260],
        "listingPlatform": str(offer.get("platform") or ""),
        "listingCurrentPoints": offer.get("currentPoints"),
        "pageTitle": normalize_space(" ".join(parser.title_parts))[:500],
        "metaDescription": normalize_space(parser.meta_description)[:1000],
        "headings": parser.headings[:24],
        "leadText": text[:MAX_DETAIL_LEAD_CHARS],
        "keywordSnippets": detail_keyword_snippets(text),
        "textLength": len(text),
        "candidateOnly": True,
        "publicationAuthorized": False,
    }


def capture_detail_evidence(offers):
    targets = load_target_config()
    evidence = []
    for offer in offers:
        game = match_target_game(offer.get("title"), targets)
        if not game:
            continue
        if len(evidence) >= MAX_DETAIL_OFFERS:
            break
        try:
            raw, final = fetch(offer["url"], ajax=False)
            item = parse_public_detail_evidence(raw, offer["url"], final, offer, game)
        except SystemExit:
            raise
        except Exception:
            item = {
                "evidenceVersion": 1,
                "adId": str(offer.get("adId") or ""),
                "gameHint": game,
                "url": str(offer.get("url") or ""),
                "state": "review_required",
                "reason": "detail_fetch_or_parse_failed",
                "candidateOnly": True,
                "publicationAuthorized": False,
            }
        evidence.append(item)
        time.sleep(0.12)
    return evidence


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
    has_ios = bool(re.search(r"(?:iOS|iPhone)\s*用", title, re.I))
    has_android = bool(re.search(r"Android\s*用", title, re.I))
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
    title = re.sub(r"\s+[0-9][0-9,]*円\(税込\)の商品ご購入で$", "", title)
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
        points = [int(value.replace(",", "")) for value in POINT_RE.findall(text)]
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

    detail_evidence = capture_detail_evidence(all_offers)

    return {
        "schemaVersion": 3,
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
        "detailEvidence": detail_evidence,
        "detailEvidenceCount": len(detail_evidence),
    }


def encode_dispatch_payload(payload):
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed).decode("ascii")
    if len(encoded) > MAX_DISPATCH_CHARS:
        raise SystemExit(
            "圧縮後データがGitHub送信上限を超えました。"
            " 手動送信用JSONへ切り替えてください。"
        )
    return encoded


def _pythonista_keychain():
    try:
        import keychain
        return keychain
    except ImportError:
        return None


def looks_like_github_token(value):
    token = str(value or "").strip()
    return (
        MIN_GITHUB_TOKEN_LEN <= len(token) <= MAX_GITHUB_TOKEN_LEN
        and GITHUB_TOKEN_RE.fullmatch(token) is not None
    )


def clipboard_github_token():
    try:
        import clipboard
        value = str(clipboard.get() or "").strip()
    except (ImportError, AttributeError):
        return ""
    return value if looks_like_github_token(value) else ""


def clear_clipboard_if_possible():
    try:
        import clipboard
        clipboard.set("")
    except (ImportError, AttributeError):
        pass


def stored_github_token():
    keychain = _pythonista_keychain()
    if keychain is None:
        return ""
    try:
        token = str(keychain.get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT) or "").strip()
    except Exception:
        return ""
    if looks_like_github_token(token):
        return token
    if token:
        try:
            keychain.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        except Exception:
            pass
    return ""


def save_github_token(token):
    keychain = _pythonista_keychain()
    if keychain is None:
        raise SystemExit(
            "PythonistaのKeychainを利用できません。"
            " この端末では自動送信を設定できません。"
        )
    keychain.set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, token)


def clear_github_token():
    keychain = _pythonista_keychain()
    if keychain is None:
        return
    try:
        keychain.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    except Exception:
        pass


def setup_github_token():
    token = clipboard_github_token()
    if not token:
        raise SystemExit(
            "GitHubトークンが未登録です。Fine-grained token をコピーしてから、"
            "このスクリプトの▶︎をもう一度押してください。手入力は不要です。"
        )
    save_github_token(token)
    clear_clipboard_if_possible()
    print("GitHubトークンをiPhoneのKeychainへ保存しました ✅")
    return token


def dispatch_to_github(encoded, token, *, open_url=urlopen):
    if not looks_like_github_token(token):
        raise SystemExit(
            "保存済みGitHubトークンが不正なため送信を停止しました。"
            " Fine-grained token をコピーしてから▶︎を押し直してください。"
        )
    body = json.dumps({
        "ref": "main",
        "inputs": {
            "point_income_catalog_base64": encoded,
        },
    }, separators=(",", ":")).encode("utf-8")
    request = Request(
        GITHUB_API,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "POIGAMELAB-PointIncome-iPhone/1.0",
        },
    )
    try:
        with open_url(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read() if hasattr(response, "read") else b""
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise SystemExit(
                "GitHubへの送信権限を確認できませんでした。"
                " トークンのリポジトリ指定と Actions: Read and write を確認してください。"
            )
        raise SystemExit(f"GitHub送信に失敗しました（HTTP {exc.code}）。")
    except URLError as exc:
        raise SystemExit("GitHubへ接続できませんでした: " + str(exc.reason))

    if status not in {200, 204}:
        raise SystemExit(f"GitHub送信が完了しませんでした（HTTP {status}）。")

    result = {"status": status}
    if status == 200 and body:
        try:
            response_data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response_data = {}
        if isinstance(response_data, dict):
            if response_data.get("workflow_run_id") is not None:
                result["workflowRunId"] = response_data.get("workflow_run_id")
            if response_data.get("html_url"):
                result["workflowUrl"] = response_data.get("html_url")
    return result


def manual_fallback(encoded):
    try:
        import clipboard
        clipboard.set(encoded)
        print("圧縮済みBase64をクリップボードへコピーしました。")
    except (ImportError, AttributeError):
        print("POINT_INCOME_GZIP_BASE64")
        print(encoded)


def main():
    if "--clear-token" in sys.argv:
        clear_github_token()
        print("保存済みGitHubトークンを削除しました。")
        return

    token = stored_github_token()
    if "--setup-token" in sys.argv or not token:
        token = setup_github_token()

    print("Point Incomeを取得しています…")
    payload = capture()
    encoded = encode_dispatch_payload(payload)

    print(json.dumps({
        "count": payload["count"],
        "pageCount": payload["pageCount"],
        "stoppedBecause": payload["stoppedBecause"],
        "pointRate": payload["pointRate"],
        "detailEvidenceCount": payload.get("detailEvidenceCount", 0),
        "compressedChars": len(encoded),
    }, ensure_ascii=False, indent=2))

    if "--manual" in sys.argv:
        manual_fallback(encoded)
        return

    dispatch_result = dispatch_to_github(encoded, token)

    print("\n送信完了 ✅")
    if dispatch_result.get("workflowRunId"):
        print("GitHub Actions run:", dispatch_result["workflowRunId"])
    print("POIGAME LAB側で検証・既存ゲーム照合・未掲載候補分離を自動実行します。")
    print("次回からはこのスクリプトの▶︎を押すだけです。")


if __name__ == "__main__":
    main()
