#!/usr/bin/env python3
import json
from pathlib import Path

path = Path("config/point_sources.json")
data = json.loads(path.read_text(encoding="utf-8"))
matched = 0
for source in data.get("sources", []):
    if source.get("id") == "hapitas":
        source["mobile"] = False
        source["reviewedAt"] = "2026-09-11"
        source["discoveryNote"] = (
            "GitHub-hosted runner probe confirmed the mobile UA redirects the public app catalog "
            "to sp.hapitas.jp with no offer identities, while a normal desktop browser UA returns "
            "the anonymous app catalog with first-party /item/detail/itemid/<id> links. Scheduled "
            "discovery therefore uses desktop UA; publication remains disabled."
        )
        matched += 1
if matched != 1:
    raise SystemExit(f"expected exactly one hapitas source, found {matched}")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
