#!/usr/bin/env python3
from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
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


def probe(source: str, url: str, ua_name: str, ua: str) -> None:
    req = Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Cache-Control": "no-cache",
    })
    try:
        with build_opener().open(req, timeout=20) as response:
            data = response.read(2_000_000)
            text = data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            matches = sorted(set(PATTERNS[source].findall(text)))
            print(
                f"RESULT source={source} ua={ua_name} status={getattr(response, 'status', 200)} "
                f"bytes={len(data)} detail_ids={len(matches)} final={response.geturl()}"
            )
            if source == "moppy":
                print(f"MARKER source=moppy ua={ua_name} searching={'検索中' in text} scripts={text.lower().count('<script')}")
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
