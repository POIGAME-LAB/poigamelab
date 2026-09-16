#!/usr/bin/env python3
"""Build one internal offer snapshot from the daily first-party crawl.

The snapshot is deliberately not a publication authority. It keeps one-site
observations, groups the same game across point sites, and records only rewards
that a reviewed source parser can express safely in JPY. It is archived to R2
and is intended to be the shared parent dataset for existing-game refresh and
future unlisted-game ranking.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import daily_scan_review as daily
import direct_offer_refresh as direct

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "refresh_policy.json"
TARGETS = ROOT / "config" / "game_targets.json"
NEW_QUEUE = ROOT / "data" / "new_game_candidate_queue.json"
REVIEW_QUEUE = ROOT / "data" / "comparison_review_queue.json"
DAILY_REVIEW = ROOT / "data" / "daily_scan_review.json"
REFRESH_STATUS = ROOT / "data" / "comparison_refresh_status.json"
OUTPUT = ROOT / "data" / "unified_offer_snapshot.json"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def game_key(value):
    cleaned = daily.discovery_name(value)
    return direct.normalized_game_title_key(cleaned)


def _better(left, right):
    """Prefer a verified/reward-bearing observation for the same offer."""
    if left is None:
        return right
    left_score = (left.get("rewardYen") is not None, bool(left.get("parserVersion")))
    right_score = (right.get("rewardYen") is not None, bool(right.get("parserVersion")))
    return right if right_score > left_score else left


def build_snapshot(*, new_items, review_items, targets, source_ids, checked_at,
                   warau_rate_confirmed=False, source_results=None):
    allowed = set(source_ids)
    known = {str(t.get("game") or "").strip(): t for t in targets if str(t.get("game") or "").strip()}
    observations = {}

    def add(obs):
        source = str(obs.get("source") or "").strip()
        game = str(obs.get("game") or "").strip()
        url = str(obs.get("url") or "").strip()
        if source not in allowed or not game or not url:
            return
        key = game_key(game)
        if not key:
            return
        identity = direct.offer_identity_key(url, source) or direct.exact_url_key(url)
        if not identity:
            return
        obs = dict(obs)
        obs["gameKey"] = key
        obs["offerIdentity"] = identity
        observations[(key, source, identity)] = _better(
            observations.get((key, source, identity)), obs
        )

    # Unlisted discovery observations are retained even with one source and even
    # when a reward parser is not available yet.
    for item in new_items or []:
        if not isinstance(item, dict) or item.get("classification") == "likely_non_game":
            continue
        game = daily.discovery_name(item.get("titleHint"))
        add({
            "game": game,
            "source": item.get("source"),
            "url": item.get("firstPartyCandidateUrl"),
            "platform": "",
            "rewardYen": None,
            "rewardVerified": False,
            "parserVersion": "",
            "listed": False,
            "titleHint": item.get("titleHint") or game,
            "observation": "first_party_listing",
        })

    # Existing-game detail observations carry the canonical game name and may
    # include exact JPY evidence from a reviewed parser.
    for item in review_items or []:
        if not isinstance(item, dict):
            continue
        game = str(item.get("game") or "").strip()
        source = str(item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        if not game or not url or source not in allowed:
            continue
        evidence = item.get("sourceEvidence") if isinstance(item.get("sourceEvidence"), dict) else {}
        reward = daily.explicit_yen(evidence, warau_rate_confirmed=warau_rate_confirmed)
        add({
            "game": game,
            "source": source,
            "url": url,
            "platform": evidence.get("platform") or item.get("platformHint") or "",
            "rewardYen": reward,
            "rewardVerified": reward is not None,
            "parserVersion": str(evidence.get("parserVersion") or ""),
            "listed": game in known,
            "titleHint": evidence.get("name") or game,
            "observation": "first_party_detail" if evidence else "first_party_listing",
        })

    groups = {}
    for obs in observations.values():
        key = obs["gameKey"]
        group = groups.setdefault(key, {
            "gameKey": key,
            "game": obs["game"],
            "listed": bool(obs.get("listed")),
            "sources": set(),
            "offers": [],
        })
        # Canonical listed names win over discovery labels.
        if obs.get("listed"):
            group["game"] = obs["game"]
            group["listed"] = True
        group["sources"].add(obs["source"])
        group["offers"].append({k: v for k, v in obs.items() if k != "gameKey"})

    out_groups = []
    for group in groups.values():
        offers = sorted(group["offers"], key=lambda x: (x["source"], x["offerIdentity"]))
        rewards = [o["rewardYen"] for o in offers if type(o.get("rewardYen")) is int]
        out_groups.append({
            "gameKey": group["gameKey"],
            "game": group["game"],
            "listed": group["listed"],
            "sourceCount": len(group["sources"]),
            "sources": sorted(group["sources"]),
            "offerCount": len(offers),
            "verifiedRewardCount": len(rewards),
            "maxVerifiedRewardYen": max(rewards) if rewards else None,
            "offers": offers,
        })
    out_groups.sort(key=lambda g: (not g["listed"], g["game"].casefold()))

    health = []
    for row in source_results or []:
        if isinstance(row, dict) and str(row.get("source") or "") in allowed:
            health.append({
                "source": str(row.get("source") or ""),
                "scanComplete": row.get("scanComplete") is True,
                "catalogComplete": row.get("catalogComplete") is True,
                "candidateCount": int(row.get("candidateCount") or 0),
                "fetchErrors": int(row.get("fetchErrors") or 0),
            })

    return {
        "phase": "UNIFIED_EIGHT_SITE_OFFER_SNAPSHOT_V1",
        "checkedAt": checked_at,
        "publicationAuthorized": False,
        "sourceIds": list(source_ids),
        "sourceCount": len(source_ids),
        "groupCount": len(out_groups),
        "listedGroupCount": sum(g["listed"] for g in out_groups),
        "unlistedGroupCount": sum(not g["listed"] for g in out_groups),
        "oneSiteGroupCount": sum(g["sourceCount"] == 1 for g in out_groups),
        "sourceHealth": sorted(health, key=lambda x: x["source"]),
        "groups": out_groups,
    }


def main():
    policy = load_json(POLICY, {})
    source_ids = [str(x).strip() for x in policy.get("unifiedDailySources", []) if str(x).strip()]
    if not source_ids:
        raise SystemExit("unifiedDailySources is empty")
    targets = load_json(TARGETS, {}).get("games") or []
    new_items = load_json(NEW_QUEUE, {}).get("items") or []
    review_items = load_json(REVIEW_QUEUE, {}).get("items") or []
    daily_report = load_json(DAILY_REVIEW, {})
    status = load_json(REFRESH_STATUS, {})
    checked_at = str(daily_report.get("checkedAt") or status.get("checkedAt") or "")
    if not checked_at:
        raise SystemExit("daily checkedAt is missing")
    snapshot = build_snapshot(
        new_items=new_items,
        review_items=review_items,
        targets=targets,
        source_ids=source_ids,
        checked_at=checked_at,
        warau_rate_confirmed=bool((daily_report.get("warauBaseRate") or {}).get("confirmed")),
        source_results=((status.get("newGameDiscovery") or {}).get("sourceResults") or []),
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({
        "phase": snapshot["phase"],
        "sources": snapshot["sourceCount"],
        "groups": snapshot["groupCount"],
        "listed": snapshot["listedGroupCount"],
        "unlisted": snapshot["unlistedGroupCount"],
        "oneSite": snapshot["oneSiteGroupCount"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
