#!/usr/bin/env python3
import json
from pathlib import Path

path = Path("config/point_sources.json")
data = json.loads(path.read_text(encoding="utf-8"))
matched = 0
for source in data.get("sources", []):
    if source.get("id") == "moppy":
        source["mobile"] = False
        source["new_game_discovery_page_url_template"] = (
            "https://pc.moppy.jp/ajax/category/get_list.php?parent_category=4&child_category=52"
            "&objective_category=&current_page={page}&af_sorter=1&exclude_purchased="
        )
        source["new_game_discovery_scope"] = "paginated_first_party_ajax_app_listing"
        source["reviewedAt"] = "2026-09-11"
        source["discoveryNote"] = (
            "GitHub-hosted runner diagnostics confirmed the public category shell loads offers via "
            "GET /ajax/category/get_list.php using parent_category, child_category, objective_category, "
            "current_page, af_sorter and exclude_purchased. The reviewed app category returned 5 "
            "first-party ad/detail.php identities on current_page=1 and an empty page on current_page=2. "
            "Scheduled discovery uses that anonymous first-party AJAX route; publication remains gated."
        )
        matched += 1
if matched != 1:
    raise SystemExit(f"expected exactly one moppy source, found {matched}")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
