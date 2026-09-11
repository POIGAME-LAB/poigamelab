#!/usr/bin/env python3
from __future__ import annotations

import html as html_lib
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener

ROUTES = {
    "moppy": [
        "https://pc.moppy.jp/category/list.php?af_sorter=1&child_category=52&page=1&parent_category=4",
    ],
    "hapitas": [
        "https://hapitas.jp/category/service_app/apn/navigation_category/",
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


def safe_moppy_hint(raw: str, base_url: str) -> str | None:
    value = html_lib.unescape(raw).strip()
    if not value or len(value) > 260 or any(ch in value for ch in ("\n", "\r", "<", ">")):
        return None
    low = value.casefold()
    if not any(marker in low for marker in (
        "ajax", "api", "category", "list.php", "site_id", "advert", "affiliate", "search", "item"
    )):
        return None
    if value.startswith(("http://", "https://", "//", "/")):
        absolute = urljoin(base_url, value)
        if urlparse(absolute).hostname not in MOPPY_HOSTS:
            return None
        return absolute
    return value


def probe_moppy_shell(page_url: str, page_html: str, ua: str) -> None:
    hints = set()

    # Inspect quoted strings, HTML attributes and inline script fragments without
    # printing response bodies or unrelated page text.
    for token in re.findall(r"[\"']([^\"']{1,260})[\"']", page_html):
        hint = safe_moppy_hint(token, page_url)
        if hint:
            hints.add(hint)

    for attr in re.findall(
        r"(?:action|href|src|data-[A-Za-z0-9_-]+)\s*=\s*[\"']([^\"']+)[\"']",
        page_html,
        re.I,
    ):
        hint = safe_moppy_hint(attr, page_url)
        if hint:
            hints.add(hint)

    # Capture literal first-party paths around common browser request APIs.
    request_fragments = re.findall(
        r"(?:fetch|ajax|get|post|load)\s*\([^)]{0,350}",
        page_html,
        re.I,
    )
    for fragment in request_fragments:
        for token in re.findall(r"[\"']([^\"']{1,260})[\"']", fragment):
            hint = safe_moppy_hint(token, page_url)
            if hint:
                hints.add(hint)

    print(f"MOPPY_SHELL_HINTS count={len(hints)}")
    for hint in sorted(hints)[:120]:
        print("MOPPY_SHELL_HINT", hint)

    srcs = []
    for raw in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", page_html, re.I):
        absolute = urljoin(page_url, raw)
        if urlparse(absolute).hostname in MOPPY_HOSTS and absolute not in srcs:
            srcs.append(absolute)
    print(f"MOPPY_JS same_origin_scripts={len(srcs)}")

    js_hints = set()
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
        print(
            f"MOPPY_JS_FETCH status={getattr(response, 'status', 200)} "
            f"bytes={len(data)} path={urlparse(response.geturl()).path}"
        )
        for token in re.findall(r"[\"']([^\"']{1,260})[\"']", text):
            hint = safe_moppy_hint(token, page_url)
            if hint:
                js_hints.add(hint)

    print(f"MOPPY_JS_HINTS count={len(js_hints)}")
    for hint in sorted(js_hints)[:120]:
        print("MOPPY_JS_HINT", hint)


def probe(source: str, url: str, ua_name: str, ua: str) -> None:
    try:
        response, data, text = request_text(url, ua)
        matches = sorted(set(PATTERNS[source].findall(text)))
        print(
            f"RESULT source={source} ua={ua_name} status={getattr(response, 'status', 200)} "
            f"bytes={len(data)} detail_ids={len(matches)} final={response.geturl()}"
        )
        if source == "moppy":
            print(
                f"MARKER source=moppy ua={ua_name} searching={'検索中' in text} "
                f"scripts={text.lower().count('<script')}"
            )
            if ua_name == "desktop":
                probe_moppy_shell(response.geturl(), text, ua)
        else:
            print(
                f"MARKER source=hapitas ua={ua_name} "
                f"app_count_marker={'全' in text and '件' in text} scripts={text.lower().count('<script')}"
            )
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
