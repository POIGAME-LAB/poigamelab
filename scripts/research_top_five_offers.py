#!/usr/bin/env python3
"""Strict offer research for the 01:17 top-five content-ready games.

External/API-assisted collection stays in quarantine. This stage never edits
production catalog, refresh policy or published offers. It reuses the existing
V28 collector and V29 deterministic gate, and emits only adoption candidates
that may later be consumed by the API-free V30 publisher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import evaluate_research_adoption as v29
import new_game_content_gate as content_gate
import research_offer_bridge as research

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "new_game_content_queue.json"
CONTENT = ROOT / "data" / "new_game_content_packages"
RESULTS = ROOT / "data" / "research_results"
CONFIG = ROOT / "config" / "trend_discovery.json"
ADOPTIONS = ROOT / "data" / "top_five_adoption_candidates.json"
STATUS = ROOT / "data" / "top_five_offer_research_status.json"
MAX_GAMES = 5


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def research_item_from_queue(row):
    game = str(row.get("game") or "").strip()
    if not game:
        raise ValueError("queue_game_missing")
    candidates = []
    sources = []
    for source in row.get("pointSiteEvidence") or []:
        if not isinstance(source, dict):
            continue
        sid = str(source.get("source") or "").strip()
        url = str(source.get("url") or "").strip()
        if sid and url:
            if sid not in sources:
                sources.append(sid)
            candidates.append({"source": sid, "url": url, "titleHint": game})
    if len(set(sources)) < 1:
        raise ValueError("queue_point_sources_missing")
    return {
        "game": game,
        "aliases": [game],
        "maxRewardPt": int(row.get("maxObservedRewardYen") or 0),
        "sources": sources,
        "sourceCandidates": candidates,
        "collectorReady": True,
        "status": "collector_ready",
        "origin": "daily_top_five_content_queue",
        "researchLogicVersion": "top-five-content-v1",
    }


def run(queue_path=QUEUE, content_dir=CONTENT, config_path=CONFIG,
        research_one=research.run_one, evaluate=v29.evaluate, env=None):
    queue = load(queue_path)
    if queue.get("phase") != "NEW_GAME_CONTENT_QUEUE_V1":
        raise ValueError("content_queue_phase_mismatch")
    cfg = load(config_path)
    env = dict(env or os.environ)
    results = []
    decisions = []
    selected = sorted((queue.get("items") or [])[:MAX_GAMES], key=lambda x: int(x.get("rank") or 999))
    for row in selected:
        game = str(row.get("game") or "").strip()
        record = {"game": game, "rank": int(row.get("rank") or 0)}
        try:
            content_gate.validate_for_game(game, content_dir=content_dir, root=ROOT)
            item = research_item_from_queue(row)
            result = research_one(item, env=env)
            record["research"] = result
            slug = research.stable_slug(game)
            result_path = RESULTS / f"{slug}.json"
            record["resultPath"] = str(result_path.relative_to(ROOT))
            if result.get("returncode") != 0 or not result.get("resultSaved") or not result_path.is_file():
                record.update(status="hold", reasons=["strict_offer_research_failed"])
                decisions.append({"game": game, "eligible": False, "status": "hold", "reasons": record["reasons"]})
            else:
                decision = evaluate(load(result_path), cfg)
                record["v29"] = decision
                if decision.get("eligible") is True and decision.get("status") == "adoption_ready":
                    record["status"] = "adoption_ready"
                    decisions.append(decision)
                else:
                    record.update(status="hold", reasons=decision.get("reasons") or ["v29_hold"])
                    decisions.append(decision)
        except Exception as exc:
            record.update(status="hold", reasons=["research_pipeline_error"], error=type(exc).__name__)
            decisions.append({"game": game, "eligible": False, "status": "hold",
                              "reasons": ["research_pipeline_error"], "error": type(exc).__name__})
        results.append(record)

    adoption_doc = {
        "schemaVersion": 1,
        "phase": "TOP_FIVE_CONTENT_ADOPTION_GATE_V1",
        "sourceQueueCheckedAt": queue.get("checkedAt"),
        "autoPublish": False,
        "autoAddGame": False,
        "items": decisions,
    }
    atomic_json(ADOPTIONS, adoption_doc)
    status = {
        "phase": "TOP_FIVE_STRICT_OFFER_RESEARCH_V1",
        "sourceQueueCheckedAt": queue.get("checkedAt"),
        "selected": len(selected),
        "researched": len(results),
        "adoptionReady": sum(x.get("status") == "adoption_ready" for x in results),
        "held": sum(x.get("status") != "adoption_ready" for x in results),
        "publicationWrites": 0,
        "results": results,
    }
    atomic_json(STATUS, status)
    return status


def main():
    if not os.getenv("GEMINI_API_KEY", "").strip():
        raise SystemExit("GEMINI_API_KEY unavailable")
    status = run()
    print(json.dumps({k: status[k] for k in ("selected", "researched", "adoptionReady", "held", "publicationWrites")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
