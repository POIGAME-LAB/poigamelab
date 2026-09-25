#!/usr/bin/env python3
"""Validate a residential-device supplied Point Income public offer catalog.

Candidate-only by design. The payload contains only public ad identities/URLs,
never HTML, cookies, account data, or login state.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_IDS = 2000
AD_RE = re.compile(r"^/ad/(\d+)/?$")
ALLOWED_HOSTS = {"pointi.jp", "www.pointi.jp", "sp.pointi.jp"}


def normalize(value):
    s = str(value or "").strip()
    if s.isdigit():
        return s
    try:
        p = urlparse(s)
    except Exception:
        return ""
    if (
        p.scheme == "https"
        and (p.hostname or "").lower() in ALLOWED_HOSTS
        and not p.query
        and not p.fragment
    ):
        m = AD_RE.fullmatch(p.path or "")
        if m:
            return m.group(1)
    return ""


def main(inp, out):
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("payload must be an object")
    if data.get("source") not in {None, "point_income"}:
        raise SystemExit("unexpected source")

    raw = data.get("adIds")
    if raw is None:
        raw = data.get("adUrls")
    if not isinstance(raw, list):
        raise SystemExit("adIds/adUrls must be a list")

    ids = []
    seen = set()
    for value in raw:
        normalized = normalize(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ids.append(normalized)

    if not ids:
        raise SystemExit("refusing empty Point Income candidate catalog")
    if len(ids) > MAX_IDS:
        raise SystemExit("refusing implausibly large Point Income catalog")

    source_url = str(data.get("sourceUrl") or "").strip()
    if source_url:
        p = urlparse(source_url)
        if p.scheme != "https" or (p.hostname or "").lower() not in ALLOWED_HOSTS:
            raise SystemExit("sourceUrl must be first-party Point Income https")

    result = {
        "schemaVersion": 1,
        "source": "point_income",
        "scope": "residential_public_offer_catalog",
        "candidateOnly": True,
        "catalogCompleteClaim": False,
        "sourceUrl": source_url,
        "pageCount": int(data.get("pageCount") or 0),
        "adIds": ids,
        "count": len(ids),
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"accepted": True, "count": len(ids)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
