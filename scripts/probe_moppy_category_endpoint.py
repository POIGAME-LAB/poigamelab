#!/usr/bin/env python3
from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

ENDPOINT = "https://pc.moppy.jp/ajax/category/get_list.php"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
CASES = [
    ("GET", {"parent_category": "4", "child_category": "52", "page": "1", "af_sorter": "1"}),
    ("GET", {"parent_category": "4", "child_category": "52", "page": "1"}),
    ("GET", {"category_id": "52", "page": "1"}),
    ("POST", {"parent_category": "4", "child_category": "52", "page": "1", "af_sorter": "1"}),
    ("POST", {"parent_category": "4", "child_category": "52", "page": "1"}),
    ("POST", {"category_id": "52", "page": "1"}),
]


def run_case(method: str, params: dict[str, str]) -> None:
    data = None
    url = ENDPOINT
    if method == "GET":
        url += "?" + urlencode(params)
    else:
        data = urlencode(params).encode("ascii")

    headers = {
        "User-Agent": UA,
        "Accept": "application/json,text/html,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Referer": "https://pc.moppy.jp/category/list.php?parent_category=4&child_category=52",
        "X-Requested-With": "XMLHttpRequest",
    }
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with build_opener().open(req, timeout=20) as response:
            body = response.read(2_000_000)
            text = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            detail_ids = sorted(set(re.findall(
                r"ad/detail\.php\?(?:[^\"'<> ]*&)?(?:site_id|s_id)=([0-9]+)", text, re.I
            )))
            site_ids = sorted(set(re.findall(r"[\"']?site_id[\"']?\s*[:=]\s*[\"']?([0-9]+)", text, re.I)))
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            print(
                "CASE",
                f"method={method}",
                f"keys={','.join(sorted(params))}",
                f"status={getattr(response, 'status', 200)}",
                f"bytes={len(body)}",
                f"content_type={content_type}",
                f"detail_ids={len(detail_ids)}",
                f"site_ids={len(site_ids)}",
                f"searching={'検索中' in text}",
            )
    except HTTPError as error:
        print("CASE", f"method={method}", f"keys={','.join(sorted(params))}", f"status={error.code}")
        error.close()
    except (URLError, TimeoutError, OSError) as error:
        print("CASE", f"method={method}", f"keys={','.join(sorted(params))}", f"error={type(error).__name__}")


def main() -> int:
    for method, params in CASES:
        run_case(method, params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
