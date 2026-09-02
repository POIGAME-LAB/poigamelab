#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build safe guide-experience update candidates from V54 research output.

Default mode NEVER edits live guide-experience JSON. It writes candidate files
under data/guide-experience-candidates/ so a human can review them first.

Only directly fetched X posts with explicit day+level progressPairs are allowed
to update the dynamic player timeline. This deliberately ignores vague posts,
blog-site identities, hearsay, and offer/deadline examples.

Existing players are matched by X account identity. Existing editorial fields
(status, summary, note) are preserved. New X accounts with explicit progress
become new candidate players (A/B/C... labels continue automatically).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V54 = ROOT / "data" / "poi_guide_experience_summary.json"
DEFAULT_LIVE_DIR = ROOT / "data" / "guide-experiences"
DEFAULT_CANDIDATE_DIR = ROOT / "data" / "guide-experience-candidates"
DEFAULT_STATUS = ROOT / "data" / "guide_experience_update_status.json"

X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def x_identity_from_url(url: str) -> str:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return ""
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or host not in X_HOSTS:
        return ""
    match = re.fullmatch(r"/([^/]+)/status/(\d+)(?:/.*)?", parsed.path or "")
    if not match:
        return ""
    return "x:" + match.group(1).casefold()


def normalize_x_identity(value: str) -> str:
    value = str(value or "").strip().casefold()
    if not value.startswith("x:"):
        return ""
    user = value[2:].strip()
    if not user or "/" in user or " " in user:
        return ""
    return "x:" + user


def player_x_identity(player: dict) -> str:
    explicit = normalize_x_identity(player.get("sourceIdentity"))
    if explicit:
        return explicit
    found = {
        x_identity_from_url(url)
        for url in (player.get("sources") or [])
        if x_identity_from_url(url)
    }
    # Multiple X accounts attached to one player is ambiguous. Fail closed.
    return next(iter(found)) if len(found) == 1 else ""


def valid_progress_pair(row) -> tuple[int, int] | None:
    if not isinstance(row, dict):
        return None
    try:
        day = int(row.get("day"))
        level = int(row.get("level"))
    except (TypeError, ValueError):
        return None
    if not (1 <= day <= 999 and 1 <= level <= 999):
        return None
    return day, level


def collect_x_progress(v54_doc: dict, game: str) -> tuple[dict, dict]:
    grouped: dict[str, dict] = {}
    diag = {
        "observationsSeen": 0,
        "eligibleDirectX": 0,
        "identityMismatch": 0,
        "noProgressPair": 0,
        "pairsAccepted": 0,
        "ignoredNonDirectX": 0,
    }

    observations = v54_doc.get("observations") if isinstance(v54_doc, dict) else []
    observations = observations if isinstance(observations, list) else []

    for row in observations:
        if not isinstance(row, dict) or str(row.get("game") or "").strip() != game:
            continue
        diag["observationsSeen"] += 1

        if row.get("origin") != "direct_x_post" or row.get("status") != "anecdotal_quarantine":
            diag["ignoredNonDirectX"] += 1
            continue

        identity = normalize_x_identity(row.get("sourceIdentity"))
        url = str(row.get("url") or "").strip()
        url_identity = x_identity_from_url(url)

        if not identity or not url_identity or identity != url_identity:
            diag["identityMismatch"] += 1
            continue

        diag["eligibleDirectX"] += 1
        pairs = []
        for pair in ((row.get("signals") or {}).get("progressPairs") or []):
            valid = valid_progress_pair(pair)
            if valid:
                pairs.append(valid)

        if not pairs:
            diag["noProgressPair"] += 1
            continue

        bucket = grouped.setdefault(identity, {"pairs": set(), "urls": set()})
        bucket["pairs"].update(pairs)
        if url:
            bucket["urls"].add(url)
        diag["pairsAccepted"] += len(pairs)

    return grouped, diag


def alpha_id(number: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    if number < 1:
        raise ValueError("number must be >= 1")
    out = ""
    n = number
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def next_player_id(players: list[dict]) -> str:
    used = {str(p.get("id") or "").strip().upper() for p in players if isinstance(p, dict)}
    i = 1
    while alpha_id(i) in used:
        i += 1
    return alpha_id(i)


def milestone_key(m: dict):
    try:
        day = int(m.get("day"))
    except (TypeError, ValueError):
        day = 10**9
    try:
        level = int(m.get("level"))
    except (TypeError, ValueError):
        level = 10**9
    return day, level, str(m.get("label") or "")


def merge_game_document(live_doc: dict, v54_doc: dict) -> tuple[dict, dict]:
    if not isinstance(live_doc, dict):
        raise ValueError("live guide experience document must be an object")
    game = str(live_doc.get("game") or "").strip()
    if not game:
        raise ValueError("live guide experience document is missing game")

    players = live_doc.get("players")
    if not isinstance(players, list):
        raise ValueError("live guide experience document players must be a list")

    result = copy.deepcopy(live_doc)
    result_players = result["players"]

    identity_to_index = {}
    identity_backfilled = 0
    for index, player in enumerate(result_players):
        if not isinstance(player, dict):
            raise ValueError("player row must be an object")
        identity = player_x_identity(player)
        if not identity:
            continue
        if identity in identity_to_index:
            raise ValueError(f"duplicate X identity in live data: {identity}")
        identity_to_index[identity] = index
        if not normalize_x_identity(player.get("sourceIdentity")):
            player["sourceIdentity"] = identity
            identity_backfilled += 1

    grouped, collection_diag = collect_x_progress(v54_doc, game)

    added_milestones = 0
    matched_players = 0
    new_players = 0
    new_player_ids = []

    for identity in sorted(grouped):
        bucket = grouped[identity]
        pairs = sorted(bucket["pairs"])
        urls = sorted(bucket["urls"])

        if identity in identity_to_index:
            matched_players += 1
            player = result_players[identity_to_index[identity]]
            existing = {
                valid_progress_pair(m)
                for m in (player.get("milestones") or [])
                if valid_progress_pair(m)
            }
            milestones = list(player.get("milestones") or [])
            for day, level in pairs:
                if (day, level) in existing:
                    continue
                milestones.append({"day": day, "level": level, "label": f"Lv{level}"})
                existing.add((day, level))
                added_milestones += 1
            milestones.sort(key=milestone_key)
            player["milestones"] = milestones

            source_urls = list(dict.fromkeys(
                [str(x) for x in (player.get("sources") or []) if str(x).strip()] + urls
            ))
            player["sources"] = source_urls
            # Preserve editorial status/summary/note exactly.
            continue

        player_id = next_player_id(result_players)
        latest_day, latest_level = max(pairs, key=lambda x: (x[0], x[1]))
        milestones = [
            {"day": day, "level": level, "label": f"Lv{level}"}
            for day, level in pairs
        ]
        result_players.append({
            "id": player_id,
            "label": f"プレイヤー{player_id}",
            "status": "ongoing",
            "summary": f"{latest_day}日目でLv{latest_level}",
            "milestones": milestones,
            "note": "自動収集で確認した進捗例。完走・撤退は未確認のため、挑戦中として掲載候補にしています。",
            "sourceIdentity": identity,
            "sources": urls,
            "reviewStatus": "new_candidate",
        })
        identity_to_index[identity] = len(result_players) - 1
        new_players += 1
        new_player_ids.append(player_id)

    generated = str(v54_doc.get("generatedAt") or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}", generated):
        result["updatedAt"] = generated[:10]

    diag = {
        "game": game,
        "playersBefore": len(players),
        "playersAfter": len(result_players),
        "matchedPlayers": matched_players,
        "identityBackfilled": identity_backfilled,
        "addedMilestones": added_milestones,
        "newPlayers": new_players,
        "newPlayerIds": new_player_ids,
        **collection_diag,
    }
    return result, diag


def run(v54_path: Path, live_dir: Path, candidate_dir: Path, apply: bool = False) -> dict:
    v54_doc = load_json(v54_path)
    if not isinstance(v54_doc, dict) or v54_doc.get("phase") != "PHASE4_POI_GUIDE_EXPERIENCE_V54":
        raise RuntimeError("V54 phase mismatch")

    files = sorted(live_dir.glob("*.json"))
    if not files:
        raise RuntimeError(f"no guide experience JSON files found in {live_dir}")

    diagnostics = []
    writes = 0

    for path in files:
        live_doc = load_json(path)
        candidate, diag = merge_game_document(live_doc, v54_doc)
        target = path if apply else candidate_dir / path.name
        write_json(target, candidate)
        writes += 1
        diag["output"] = str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target)
        diagnostics.append(diag)

    return {
        "phase": "GUIDE_EXPERIENCE_UPDATE_CANDIDATES_V1",
        "generatedAt": now_iso(),
        "mode": "apply" if apply else "candidate",
        "sourcePhase": v54_doc.get("phase"),
        "sourceGeneratedAt": v54_doc.get("generatedAt"),
        "filesProcessed": len(files),
        "writes": writes,
        "publicationWrites": writes if apply else 0,
        "diagnostics": diagnostics,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v54", type=Path, default=DEFAULT_V54)
    parser.add_argument("--live-dir", type=Path, default=DEFAULT_LIVE_DIR)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run(args.v54, args.live_dir, args.candidate_dir, apply=args.apply)
    write_json(args.status, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
