#!/usr/bin/env python3
from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

ROUTES = {
    "moppy": [
        "https://pc.moppy.jp/category/list.php?af_sorter=1&child_category=52&page=1&parent_category=4",
        "https://pc.moppy.jp/category/list.php?parent_category=4&child_category=52",
        "https://moppy.jp/category/list.php?af_sorter=1&child_category=52&page=1&parent_category=4",
    ],
    "hapitas": [
        "https://hapitas.jp/category/service_app/apn/navigation_category/",
        "https://hapitas.jp/category/service_app/",
        "https://www.hapitas.jp/category/service_app/apn/navigation_category/",
    ],
}

UAS = {
    "mobile": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "desktop": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
    ),
}

PATTERNS = {
    "moppy": re.compile(r"(?:ad/detail\.php\?(?:[^\"'<> ]*&)?(?:site_id|s_id)=\d+)", re.I),
    "hapitas": re.compile(r"/item/detail/itemid/\d+", re.I),
}

MOPPY_HOSTS = {"pc.moppy.jp", "moppy.jp"}


def request_text(url: str, ua: str, limit: int = 2_000_000):
    req = Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Cache-Control": "no-cache",
    })
    with build_opener().open(req, timeout=20) as response:
        data = response.read(limit)
        text = data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return response, data, text


def probe_moppy_scripts(page_url: str, html: str, ua: str) -> None:
    srcs = []
    for raw in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I):
        absolute = urljoin(page_url, raw)
        if urlparse(absolute).hostname in MOPPY_HOSTS and absolute not in srcs:
            srcs.append(absolute)
    print(f"MOPPY_JS same_origin_scripts={len(srcs)}")

    hints = set()
    for script_url in srcs[:30]:
        try:
            response, data, text = request_text(script_url, ua, limit=750_000)
        except Exception as error:
            if isinstance(error, HTTPError):
                try:
                    error.close()
                except OSError:
                    pass
            print(f"MOPPY_JS_FETCH error={type(error).__name__} path={urlparse(script_url).path}")
            continue

        path = urlparse(response.geturl()).path
        print(f"MOPPY_JS_FETCH status={getattr(response, 'status', 200)} bytes={len(data)} path={path}")
        for token in re.findall(r"[\"']([^\"']{1,220})[\"']", text):
            low = token.lower()
            if not any(marker in low for marker in ("ajax", "api", "category", "list.php", "site_id", "advert", "search")):
                continue
            if token.startswith(("http://", "https://")):
                parsed = urlparse(token)
                if parsed.hostname not in MOPPY_HOSTS:
                    continue
            if any(ch in token for ch in ("\n", "\r", "<", ">")):
                continue
            hints.add(token)

    for hint in sorted(hints)[:80]:
        print("MOPPY_HINT", hint)


def probe(source: str, url: str, ua_name: str, ua: str) -> None:
    try:
        response, data, text = request_text(url, ua)
        matches = sorted(set(PATTERNS[source].findall(text)))
        print(
            f"RESULT source={source} ua={ua_name} status={getattr(response, 'status', 200)} "
            f"bytes={len(data)} detail_ids={len(matches)} final={response.geturl()}"
        )
        if source == "moppy":
            print(f"MARKER source=moppy ua={ua_name} searching={'検索中' in text} scripts={text.lower().count('<script')}")
            if ua_name == "desktop" and "af_sorter=1" in url:
                probe_moppy_scripts(response.geturl(), text, ua)
        else:
            print(f"MARKER source=hapitas ua={ua_name} app_count_marker={'全' in text and '件' in text} scripts={text.lower().count('<script')}")
    except HTTPError as error:
        print(f"RESULT source={source} ua={ua_name} status={error.code} http_error=true url={url}")
        error.close()
    except (URLError, TimeoutError, OSError) as error:
        print(f"RESULT source={source} ua={ua_name} network_error={type(error).__name__} url={url}")


def main() -> int:
    for source, urls in ROUTES.items():
        for url in urls:
            for ua_name, ua in UAS.items():
                probe(source, url, ua_name, ua)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
