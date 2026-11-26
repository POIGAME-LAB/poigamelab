#!/usr/bin/env python3
"""Check that a day's guide selection really examined enough games for player records (operator decision 2026-11-26).

Before this rule the routine read 29 offers but searched player records for only 2-4 games a day, so most days ended
with 0-1 articles. From 2026-11-27 a batch must have searched player records for at least
``MIN_DEEP_DIVES`` games (or every ``offer_verified`` game when there are fewer), unless it already completed five
articles. Each searched game is recorded in ``selection.json`` ``decisions`` with ``decision`` "completed" or "held"
and a ``playerSearch`` object::

    {"game": "...", "decision": "held", "reason": "...",
     "playerSearch": {"queries": ["<ゲーム名> ポイ活", "..."], "recordsFound": 1, "independentPlayers": 1}}

The quality bar itself (2 independent players, 3 records, <= 5 years, > 1 year only with today's condition) is not
changed here; this only checks that the search was done for enough games.

    python scripts/check_daily_selection.py research/daily-guides/2026-11-27
    python scripts/check_daily_selection.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "research" / "daily-guides"
MIN_DEEP_DIVES = 10
MAX_ARTICLES_PER_DAY = 5
RULE_FROM = "2026-11-27"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def problems(batch: Path) -> list[str]:
    date = batch.name
    if date < RULE_FROM:
        return []
    sel_path, tri_path = batch / "selection.json", batch / "triage.json"
    if not sel_path.is_file():
        return ["missing_selection_json"]
    sel = _json(sel_path)
    decisions = sel.get("decisions", [])
    completed = [d for d in decisions if d.get("decision") == "completed"]
    if len(completed) >= MAX_ARTICLES_PER_DAY:
        return []
    verified = None
    if tri_path.is_file():
        tri = _json(tri_path)
        verified = sum(1 for i in tri.get("items", []) if i.get("verdict") == "offer_verified" and i.get("bucket") != "non_game_or_service")
    required = MIN_DEEP_DIVES if verified is None else min(MIN_DEEP_DIVES, verified)
    out = []
    searched = []
    for d in decisions:
        if d.get("decision") not in ("completed", "held"):
            continue
        ps = d.get("playerSearch")
        if not isinstance(ps, dict) or not ps.get("queries") or not isinstance(ps.get("recordsFound"), int):
            out.append(f"player_search_not_recorded:{d.get('game')}")
            continue
        searched.append(d.get("game"))
    if len(set(searched)) < required:
        out.append(f"too_few_player_searches:{len(set(searched))}<{required}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("batch", nargs="?", help="research/daily-guides/<date>")
    ap.add_argument("--all", action="store_true", help="check every dated batch")
    args = ap.parse_args(argv)
    batches = sorted(p for p in DAILY_DIR.glob("20??-??-??") if p.is_dir()) if args.all else [Path(args.batch)]
    bad = {}
    for b in batches:
        errs = problems(b)
        if errs:
            bad[b.name] = errs
        print(f"{b.name}: {'ok' if not errs else '; '.join(errs)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
