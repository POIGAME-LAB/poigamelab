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


def probe_page(page: int) -> tuple[str, ...]:
    params = {
        "parent_category": "4",
        "child_category": "52",
        "objective_category": "",
        "current_page": str(page),
        "af_sorter": "1",
        "exclude_purchased": "",
    }
    url = ENDPOINT + "?" + urlencode(params)
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
        "Referer": LISTING,
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        with build_opener().open(req, timeout=20) as response:
            body = response.read(2_000_000)
            text = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            detail_ids = tuple(sorted(set(re.findall(
                r"ad/detail\.php\?(?:[^\"'<> ]*&)?(?:site_id|s_id)=([0-9]+)", text, re.I
            ))))
            print(
                "PAGE",
                f"page={page}",
                f"status={getattr(response, 'status', 200)}",
                f"bytes={len(body)}",
                f"detail_ids={len(detail_ids)}",
                f"signature={','.join(detail_ids[:5])}",
            )
            return detail_ids
    except HTTPError as error:
        print("PAGE", f"page={page}", f"status={error.code}")
        error.close()
    except (URLError, TimeoutError, OSError) as error:
        print("PAGE", f"page={page}", f"error={type(error).__name__}")
    return tuple()


def main() -> int:
    seen = set()
    total = set()
    for page in range(1, 31):
        ids = probe_page(page)
        if not ids:
            print(f"STOP empty_page={page} unique_total={len(total)}")
            break
        if ids in seen:
            print(f"STOP repeated_page={page} unique_total={len(total)}")
            break
        seen.add(ids)
        total.update(ids)
    else:
        print(f"STOP cap_reached=30 unique_total={len(total)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
