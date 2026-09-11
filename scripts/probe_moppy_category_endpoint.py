#!/usr/bin/env python3
from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

ENDPOINT = "https://pc.moppy.jp/ajax/category/get_list.php"
LISTING = "https://pc.moppy.jp/category/list.php?af_sorter=1&child_category=52&page=1&parent_category=4"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)


def get_text(url: str) -> str:
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Referer": LISTING,
        "X-Requested-With": "XMLHttpRequest",
    })
    with build_opener().open(req, timeout=20) as response:
        body = response.read(2_000_000)
        return body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def print_contract_context() -> None:
    text = get_text(LISTING)
    needle = "/ajax/category/get_list.php"
    pos = text.find(needle)
    if pos < 0:
        print("CONTRACT endpoint_not_found")
        return
    context = text[max(0, pos - 1000):pos + 1800]
    context = re.sub(r"\s+", " ", context).strip()
    # Keep only a bounded code excerpt around the public first-party endpoint.
    print("CONTRACT_CONTEXT", context[:2800])


def probe(params: dict[str, str]) -> tuple[str, ...]:
    url = ENDPOINT + "?" + urlencode(params)
    try:
        text = get_text(url)
        detail_ids = tuple(sorted(set(re.findall(
            r"ad/detail\.php\?(?:[^\"'<> ]*&)?(?:site_id|s_id)=([0-9]+)", text, re.I
        ))))
        print(
            "CASE",
            f"params={urlencode(params)}",
            f"bytes={len(text.encode('utf-8'))}",
            f"detail_ids={len(detail_ids)}",
            f"signature={','.join(detail_ids[:5])}",
        )
        return detail_ids
    except HTTPError as error:
        print("CASE", f"params={urlencode(params)}", f"status={error.code}")
        error.close()
    except (URLError, TimeoutError, OSError) as error:
        print("CASE", f"params={urlencode(params)}", f"error={type(error).__name__}")
    return tuple()


def main() -> int:
    print_contract_context()
    variants = [
        {"parent_category": "4", "child_category": "52", "page": "1", "af_sorter": "1"},
        {"parent_category": "4", "child_category": "52", "page": "2", "af_sorter": "1"},
        {"parent_category": "4", "child_category": "52", "offset": "5", "af_sorter": "1"},
        {"parent_category": "4", "child_category": "52", "start": "5", "af_sorter": "1"},
        {"parent_category": "4", "child_category": "52", "p": "2", "af_sorter": "1"},
    ]
    for params in variants:
        probe(params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
