#!/usr/bin/env python3
"""PHASE 3 V27: promote strong trend candidates into a collector research queue.

This stage is deliberately API-free and non-publishing. It consumes only the
V26 trend candidate file, applies deterministic Python rules, and writes a
research queue for the future offer collector bridge. It never edits games.csv,
game_targets.json, offers.csv, or published_offers.csv.
"""
from __future__ import annotations
import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "trend_discovery.json"
NOW = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_key(value):
    return " ".join((value or "").strip().lower().split())


def known_names(root=ROOT):
    names = set()
    games_csv = root / "games.csv"
    if games_csv.exists():
        with games_csv.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("name"):
                    names.add(normalize_key(row["name"]))
    targets = root / "config" / "game_targets.json"
    if targets.exists():
        for item in load_json(targets).get("games", []):
            for value in [item.get("game"), *(item.get("aliases") or [])]:
                if value:
                    names.add(normalize_key(value))
    return names


def promotion_decision(candidate, cfg, known=None):
    known = known if known is not None else known_names()
    reasons = []
    game = (candidate.get("game") or "").strip()
    aliases = candidate.get("aliases") or []
    identity = {normalize_key(game), *(normalize_key(x) for x in aliases)} - {""}

    if not game:
        reasons.append("missing_game_name")
    if candidate.get("knownGame") or identity.intersection(known):
        reasons.append("known_game")

    min_score = int(cfg.get("minimumScoreForResearch", 60))
    min_conf = int(cfg.get("minimumConfidenceForResearch", 70))
    min_sources = int(cfg.get("minimumSourcesForResearch", 2))
    if int(candidate.get("score") or 0) < min_score:
        reasons.append("score_below_threshold")
    if int(candidate.get("confidence") or 0) < min_conf:
        reasons.append("confidence_below_threshold")
    if int(candidate.get("sourceCount") or 0) < min_sources:
        reasons.append("insufficient_independent_sources")

    evidence = candidate.get("evidence") or []
    types = {e.get("sourceType") for e in evidence}
    if cfg.get("requirePointSiteEvidenceForResearch", True) and "point_site" not in types:
        reasons.append("no_point_site_evidence")

    return len(reasons) == 0, reasons


def build_research_queue(trend_result, cfg, previous=None, known=None, now=None):
    now = now or NOW
    previous = previous or {}
    previous_by_key = {
        normalize_key(x.get("game")): x
        for x in previous.get("items", []) if x.get("game")
    }
    items = []
    rejected = []
    seen = set()

    for candidate in trend_result.get("candidates", []):
        key = normalize_key(candidate.get("game"))
        if not key or key in seen:
            continue
        seen.add(key)
        ok, reasons = promotion_decision(candidate, cfg, known=known)
        if not ok:
            rejected.append({"game": candidate.get("game", ""), "reasons": reasons})
            continue
        old = previous_by_key.get(key, {})
        items.append({
            "game": candidate["game"],
            "aliases": candidate.get("aliases") or [],
            "status": "collector_ready",
            "collectorReady": True,
            "firstPromotedAt": old.get("firstPromotedAt") or now,
            "lastConfirmedAt": now,
            "score": int(candidate.get("score") or 0),
            "confidence": int(candidate.get("confidence") or 0),
            "sourceCount": int(candidate.get("sourceCount") or 0),
            "sourceTypeCount": int(candidate.get("sourceTypeCount") or 0),
            "evidence": candidate.get("evidence") or [],
        })

    items.sort(key=lambda x: (-x["score"], -x["confidence"], x["game"].lower()))
    return {
        "schemaVersion": 1,
        "generatedAt": now,
        "sourceGeneratedAt": trend_result.get("generatedAt"),
        "candidateOnly": True,
        "autoPublish": False,
        "autoAddToGameTargets": False,
        "apiCalls": 0,
        "summary": {
            "trendCandidates": len(trend_result.get("candidates", [])),
            "collectorReady": len(items),
            "rejected": len(rejected),
        },
        "items": items,
        "rejected": rejected,
    }


def run(trend_path=None, config_path=None, output_path=None):
    trend_path = Path(trend_path or DATA / "trend_candidates.json")
    config_path = Path(config_path or CONFIG)
    output_path = Path(output_path or DATA / "research_queue.json")
    if not trend_path.exists():
        raise FileNotFoundError(f"trend candidate file not found: {trend_path}")
    cfg = load_json(config_path)
    trend = load_json(trend_path)
    previous = load_json(output_path) if output_path.exists() else {}
    result = build_research_queue(trend, cfg, previous=previous)
    atomic_json(output_path, result)
    return result


def main():
    result = run()
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
