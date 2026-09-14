#!/usr/bin/env python3
"""Enable daily direct refresh only for newly adopted games that still pass strict safety checks.

This is the post-adoption handoff between V29/V30 production adoption and the
existing API-free daily comparison refresh. It performs no network/API calls.
A game is enabled only when the recorded V29 decision is eligible, V30 actually
adopted it, the game exists in the catalog, and published verified rows contain
at least the policy-required number of independent point sites.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_STATUS = ROOT / "data" / "high_reward_adoption_status.json"
REFRESH_POLICY = ROOT / "config" / "refresh_policy.json"
PUBLISHED = ROOT / "data" / "published_offers.csv"
GAMES = ROOT / "games.csv"
STATUS = ROOT / "data" / "adopted_refresh_status.json"


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def norm(text):
    return "".join(str(text or "").casefold().split())


def truthy(value):
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def read_csv(path):
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run(
    bridge_status_path=BRIDGE_STATUS,
    refresh_policy_path=REFRESH_POLICY,
    published_path=PUBLISHED,
    games_path=GAMES,
    status_path=STATUS,
):
    bridge = load_json(bridge_status_path) if Path(bridge_status_path).exists() else {"results": []}
    policy = load_json(refresh_policy_path)
    published = read_csv(published_path)
    games = {norm(row.get("name")) for row in read_csv(games_path) if row.get("name")}
    required_sources = int(policy.get("minimumConfirmedSourcesForComparison", 2) or 2)

    published_by_game = {}
    for row in published:
        game = str(row.get("game") or "").strip()
        if not game or not truthy(row.get("verified")):
            continue
        published_by_game.setdefault(norm(game), []).append(row)

    decisions = []
    enabled_now = 0
    already_enabled = 0
    eligible_adoptions = 0

    for row in bridge.get("results") or []:
        if not isinstance(row, dict) or row.get("status") != "adopted":
            continue
        eligible_adoptions += 1
        game = str(row.get("game") or "").strip()
        v29 = row.get("v29") or {}
        v30 = row.get("v30") or {}
        reasons = []

        if not game:
            reasons.append("missing_game")
        if v29.get("eligible") is not True:
            reasons.append("v29_not_eligible")
        if int(v29.get("verifiedSourceCount") or 0) < required_sources:
            reasons.append("v29_insufficient_verified_sources")
        if v30.get("adopted") is not True:
            reasons.append("v30_not_adopted")
        if game and norm(game) not in games:
            reasons.append("catalog_missing")

        rows = published_by_game.get(norm(game), []) if game else []
        sites = {str(x.get("site") or "").strip() for x in rows if str(x.get("site") or "").strip()}
        if len(sites) < required_sources:
            reasons.append("published_independent_sources_insufficient")

        entry = (policy.setdefault("games", {}).get(game) if game else None) or {}
        if reasons:
            decisions.append({
                "game": game,
                "enabled": False,
                "reasons": reasons,
                "publishedVerifiedSources": sorted(sites),
            })
            continue

        was_enabled = bool(entry.get("enabled"))
        entry["enabled"] = True
        entry.setdefault("supplementalSources", [])
        entry["adoptedBy"] = entry.get("adoptedBy") or "V30"
        entry["autoEnabledBy"] = "POST_ADOPTION_REFRESH_V1"
        entry["autoEnabledAt"] = now_iso()
        policy.setdefault("games", {})[game] = entry

        if was_enabled:
            already_enabled += 1
        else:
            enabled_now += 1
        decisions.append({
            "game": game,
            "enabled": True,
            "alreadyEnabled": was_enabled,
            "publishedVerifiedSources": sorted(sites),
        })

    atomic_json(refresh_policy_path, policy)
    status = {
        "phase": "POST_ADOPTION_REFRESH_V1",
        "runAt": now_iso(),
        "apiCalls": 0,
        "eligibleAdoptions": eligible_adoptions,
        "enabledNow": enabled_now,
        "alreadyEnabled": already_enabled,
        "held": sum(1 for x in decisions if not x.get("enabled")),
        "results": decisions,
    }
    atomic_json(status_path, status)
    return status


def main():
    out = run()
    print(json.dumps({k: out[k] for k in ("eligibleAdoptions", "enabledNow", "alreadyEnabled", "held")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
