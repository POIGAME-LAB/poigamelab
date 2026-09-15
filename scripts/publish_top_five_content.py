#!/usr/bin/env python3
"""API-free publication bridge for researched top-five new games.

All external research must already be complete. This stage checks that the exact
research bundle belongs to the current 01:17 queue, runs V30 with the strict
content package gate, enables safe daily refresh for adopted games, and persists
only compact guide metadata. No network or AI calls occur here.
"""
from __future__ import annotations

import json
from pathlib import Path

import adopt_verified_games as v30
import enable_adopted_refresh as enable_refresh
import register_generated_guides as registry

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "new_game_content_queue.json"
ADOPTIONS = ROOT / "data" / "top_five_adoption_candidates.json"
RESULTS = ROOT / "data" / "research_results"
CONTENT = ROOT / "data" / "new_game_content_packages"
V30_STATUS = ROOT / "data" / "top_five_v30_status.json"
BRIDGE = ROOT / "data" / "top_five_post_adoption_bridge.json"
REFRESH_STATUS = ROOT / "data" / "top_five_refresh_enable_status.json"
STATUS = ROOT / "data" / "top_five_publication_status.json"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_handoff(queue, adoptions):
    if queue.get("phase") != "NEW_GAME_CONTENT_QUEUE_V1":
        raise ValueError("publication_queue_phase_mismatch")
    if adoptions.get("phase") != "TOP_FIVE_CONTENT_ADOPTION_GATE_V1":
        raise ValueError("publication_adoption_phase_mismatch")
    checked = str(queue.get("checkedAt") or "")
    if not checked or str(adoptions.get("sourceQueueCheckedAt") or "") != checked:
        raise ValueError("publication_bundle_stale")
    ranked = [str(x.get("game") or "").strip() for x in (queue.get("items") or [])[:5]]
    if len(ranked) != len(set(ranked)) or any(not x for x in ranked):
        raise ValueError("publication_queue_game_identity_invalid")
    allowed = set(ranked)
    for row in adoptions.get("items") or []:
        game = str((row or {}).get("game") or "").strip() if isinstance(row, dict) else ""
        if not game or game not in allowed:
            raise ValueError("publication_adoption_game_outside_queue")
    return ranked


def bridge_rows(adoptions, v30_status):
    v30_by_game = {str(x.get("game") or ""): x for x in (v30_status.get("results") or []) if isinstance(x, dict)}
    rows = []
    for v29 in adoptions.get("items") or []:
        if not isinstance(v29, dict):
            continue
        game = str(v29.get("game") or "").strip()
        outcome = v30_by_game.get(game, {"game": game, "adopted": False, "reasons": ["v30_result_missing"]})
        rows.append({
            "game": game,
            "status": "adopted" if outcome.get("adopted") is True else "hold",
            "v29": v29,
            "v30": outcome,
        })
    return rows


def run(queue_path=QUEUE, adoptions_path=ADOPTIONS, results_dir=RESULTS, content_dir=CONTENT,
        root=ROOT, status_path=STATUS):
    queue = load(queue_path)
    adoptions = load(adoptions_path)
    ranked = validate_handoff(queue, adoptions)
    before = {str(x.get("name") or "").strip() for x in v30.read_csv(Path(root) / "games.csv")}

    v30_status = v30.run(
        adoptions_path=adoptions_path,
        results_dir=results_dir,
        games_path=Path(root) / "games.csv",
        targets_path=Path(root) / "config/game_targets.json",
        refresh_path=Path(root) / "config/refresh_policy.json",
        published_path=Path(root) / "data/published_offers.csv",
        status_path=V30_STATUS,
        config_path=Path(root) / "config/trend_discovery.json",
        content_dir=content_dir,
        content_root=root,
    )
    bridge = {
        "phase": "TOP_FIVE_POST_ADOPTION_BRIDGE_V1",
        "sourceQueueCheckedAt": queue.get("checkedAt"),
        "results": bridge_rows(adoptions, v30_status),
    }
    atomic_json(BRIDGE, bridge)
    refresh_status = enable_refresh.run(
        bridge_status_path=BRIDGE,
        refresh_policy_path=Path(root) / "config/refresh_policy.json",
        published_path=Path(root) / "data/published_offers.csv",
        games_path=Path(root) / "games.csv",
        status_path=REFRESH_STATUS,
    )
    guide_status = registry.run(
        root=root,
        content_dir=content_dir,
        registry_path=Path(root) / "data/generated_guides_registry.json",
        guides_js=Path(root) / "site-guides.js",
        sitemap=Path(root) / "sitemap.xml",
    )
    after = {str(x.get("name") or "").strip() for x in v30.read_csv(Path(root) / "games.csv")}
    added = [game for game in ranked if game in after and game not in before]
    status = {
        "phase": "TOP_FIVE_CONTENT_PUBLICATION_V1",
        "sourceQueueCheckedAt": queue.get("checkedAt"),
        "rankedGames": ranked,
        "adopted": int(v30_status.get("adopted") or 0),
        "held": int(v30_status.get("held") or 0),
        "addedGames": added,
        "refreshEnabledNow": int(refresh_status.get("enabledNow") or 0),
        "registeredGuides": int(guide_status.get("registered") or 0),
        "apiCalls": 0,
    }
    atomic_json(status_path, status)
    return status


def main():
    status = run()
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
