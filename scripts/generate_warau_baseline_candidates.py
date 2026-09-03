#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECT_PATH = Path(__file__).with_name("direct_offer_refresh.py")
_spec = importlib.util.spec_from_file_location("poigamelab_direct_offer_refresh", DIRECT_PATH)
direct = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(direct)

DEFAULT_GAMES = ("メメントモリ", "ホワイトアウト・サバイバル")
UNIT_CONVERSION = {
    "sourceUnit": "pt",
    "targetUnit": "JPY",
    "yenPerPoint": 1,
    "evidenceUrl": "https://www.warau.jp/help/qa/128/",
}


def load_rows(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_candidate(row, evidence, checked_on):
    if row.get("site") != "warau" or row.get("verified") != "true":
        raise ValueError("published_row_not_verified_warau")
    if evidence.get("state") != "parsed" or evidence.get("parserVersion") != "warau-stepup-v1":
        state = str(evidence.get("state") or "unknown")[:40]
        reason = str(evidence.get("reason") or "unspecified")[:80]
        raise ValueError(f"source_evidence_not_supported:{state}:{reason}")
    if not row.get("offerKey") or row.get("game") == "":
        raise ValueError("missing_published_identity")
    try:
        row_offer_id = direct.warau_offer_id(row.get("url", ""))
        source_offer_id = direct.warau_offer_id(row.get("sourceUrl", ""))
    except ValueError as error:
        raise ValueError("published_identity_invalid") from error
    if row_offer_id != source_offer_id or row_offer_id != evidence.get("offerId"):
        raise ValueError("published_identity_mismatch")
    if row.get("platform") != evidence.get("platform"):
        raise ValueError("published_platform_mismatch")
    reward = str(row.get("reward") or "")
    if not reward.isdigit() or int(reward) != evidence.get("rewardPoints"):
        raise ValueError("published_reward_mismatch")
    steps = evidence.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("missing_step_evidence")

    return {
        "offerKey": row["offerKey"],
        "game": row["game"],
        "source": "warau",
        "approved": False,
        "sourceCheckedOn": checked_on,
        "sourceUrl": row["sourceUrl"],
        "parserVersion": evidence["parserVersion"],
        "evidenceFingerprint": evidence["evidenceFingerprint"],
        "publishedRowFingerprint": direct.published_row_fingerprint(row),
        "stepCount": len(steps),
        "rewardPoints": evidence["rewardPoints"],
        "unitConversion": dict(UNIT_CONVERSION),
    }


def generate_candidates(games=DEFAULT_GAMES, fetcher=None, root=ROOT, checked_on=None):
    fetcher = fetcher or direct.fetch_first_party
    checked_on = checked_on or datetime.now().astimezone().date().isoformat()
    games = tuple(dict.fromkeys(str(game).strip() for game in games if str(game).strip()))
    if not games:
        raise ValueError("no_games_requested")

    targets = json.loads((root / "config" / "game_targets.json").read_text(encoding="utf-8"))
    source_payload = json.loads((root / "config" / "point_sources.json").read_text(encoding="utf-8"))
    rows = load_rows(root / "data" / "published_offers.csv")
    source = next((item for item in source_payload.get("sources", []) if item.get("id") == "warau"), None)
    if not isinstance(source, dict):
        raise ValueError("warau_source_missing")

    target_by_game = {
        item.get("game"): item for item in targets.get("games", [])
        if isinstance(item, dict) and item.get("game")
    }
    candidates = []
    failures = []

    for game in games:
        target = target_by_game.get(game)
        if target is None:
            failures.append({"game": game, "reason": "target_missing"})
            continue
        aliases = [game] + [str(x) for x in (target.get("aliases") or []) if str(x).strip()]
        urls = ((target.get("known_urls_by_source") or {}).get("warau") or [])
        if not urls:
            failures.append({"game": game, "reason": "warau_target_urls_missing"})
            continue

        seen_ids = set()
        for url in urls:
            try:
                if not direct.source_host_allowed(url, source):
                    raise ValueError("target_url_not_registered_first_party")
                offer_id = direct.warau_offer_id(url)
                if offer_id in seen_ids:
                    raise ValueError("duplicate_target_offer_identity")
                seen_ids.add(offer_id)
                matching = [
                    row for row in rows
                    if row.get("game") == game
                    and row.get("site") == "warau"
                    and direct.warau_offer_id(row.get("url", "")) == offer_id
                ]
                if len(matching) != 1:
                    raise ValueError("published_row_identity_not_unique")
                raw, final_url = fetcher(url, source)
                evidence = direct.inspect_warau_offer(raw, url, final_url, aliases)
                candidates.append(build_candidate(matching[0], evidence, checked_on))
            except Exception as error:
                failures.append({
                    "game": game,
                    "url": url,
                    "reason": str(error)[:120] or error.__class__.__name__,
                })

    candidates.sort(key=lambda item: (item["game"], item["offerKey"]))
    return {
        "schemaVersion": 1,
        "mode": "candidate_only_read_only",
        "complete": not failures,
        "requestedGames": list(games),
        "candidateCount": len(candidates),
        "failureCount": len(failures),
        "candidates": candidates,
        "failures": failures,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read Warau first-party pages and print unapproved baseline candidates. No repository file is written."
    )
    parser.add_argument(
        "--games",
        nargs="+",
        default=list(DEFAULT_GAMES),
        help="Exact game names from config/game_targets.json",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = generate_candidates(args.games)
    except Exception as error:
        print(json.dumps({
            "schemaVersion": 1,
            "mode": "candidate_only_read_only",
            "complete": False,
            "candidateCount": 0,
            "failureCount": 1,
            "candidates": [],
            "failures": [{"reason": str(error)[:120] or error.__class__.__name__}],
        }, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
