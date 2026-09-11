#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

ROOT_FILES = (
    "index.html",
    "game.html",
    "guides.html",
    "offers.html",
    "kinoko-guide.html",
    "mementomori-guide.html",
    "township-lv60.html",
    "township-lv70.html",
    "whiteout-survival-guide.html",
    "working-heroes-guide.html",
    "tokyo-debunker-guide.html",
    "puzzles-survival-guide.html",
    "kingshot-guide.html",
    "houchishojo-guide.html",
    "evertale-guide.html",
    "data-status.html",
    "new-game-status.html",
    "existing-game-status.html",
    "about.html",
    "privacy.html",
    "contact.html",
    "404.html",
    "games.csv",
    "games.js",
    "site-data.js",
    "site-footer.js",
    "site-referrals.js",
    "site-guides.js",
    "site-image-rights.js",
    "site-header.js",
    "poigamelab_hero.png",
    "poigamelab_icon.png",
    "poigamelab_logo_horizontal.png",
    "robots.txt",
    "sitemap.xml",
    "CNAME",
)

DATA_FILES = (
    "published_offers.csv",
    "offer_history.csv",
    "refresh_status.json",
    "exception_queue.json",
)

CONFIG_FILES = (
    "refresh_policy.json",
)

PUBLIC_DIRS = (
    "assets",
)

DATA_DIRS = (
    "guide-experiences",
)


def _safe_source(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing_public_source:{path.relative_to(ROOT)}")
    if path.is_symlink():
        raise ValueError(f"symlink_public_source_rejected:{path.relative_to(ROOT)}")


def _copy_file(source: Path, destination: Path) -> None:
    _safe_source(source)
    if not source.is_file():
        raise ValueError(f"public_source_not_file:{source.relative_to(ROOT)}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree(source: Path, destination: Path) -> None:
    _safe_source(source)
    if not source.is_dir():
        raise ValueError(f"public_source_not_directory:{source.relative_to(ROOT)}")
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink_public_source_rejected:{path.relative_to(ROOT)}")
        if path.is_file():
            relative = path.relative_to(source)
            _copy_file(path, destination / relative)


def _safe_monitor_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return raw


def _load_optional_json(path: Path, default):
    if not path.exists() or path.is_symlink():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    return value


def _public_candidate(item):
    if not isinstance(item, dict):
        return None
    return {
        "titleHint": str(item.get("titleHint") or ""),
        "source": str(item.get("source") or ""),
        "classification": str(item.get("classification") or "review"),
        "discoveryScope": str(item.get("discoveryScope") or ""),
        "firstSeen": item.get("firstSeen"),
        "isNewToday": item.get("isNewToday") is True,
        "firstPartyCandidateUrl": _safe_monitor_url(item.get("firstPartyCandidateUrl")),
    }


def _build_new_game_monitor_snapshot() -> dict:
    queue = _load_optional_json(ROOT / "data" / "new_game_candidate_queue.json", {})
    history = _load_optional_json(ROOT / "data" / "new_game_candidate_history.json", {})
    refresh = _load_optional_json(ROOT / "data" / "comparison_refresh_status.json", {})

    raw_items = queue.get("items") if isinstance(queue, dict) else []
    candidates = [
        value for value in (_public_candidate(item) for item in (raw_items or []))
        if value is not None
    ]

    raw_priority = queue.get("reviewPriority") if isinstance(queue, dict) else []
    priority = []
    for item in raw_priority or []:
        if not isinstance(item, dict):
            continue
        priority.append({
            "titleHint": str(item.get("titleHint") or ""),
            "source": str(item.get("source") or ""),
            "classification": str(item.get("classification") or "review"),
            "sourceCount": int(item.get("sourceCount") or 0),
            "reviewPriorityScore": int(item.get("reviewPriorityScore") or 0),
            "reviewPriority": str(item.get("reviewPriority") or "low"),
        })

    history_items = []
    raw_history = history.get("items") if isinstance(history, dict) else {}
    if isinstance(raw_history, dict):
        for item in raw_history.values():
            if not isinstance(item, dict):
                continue
            history_items.append({
                "titleHint": str(item.get("titleHint") or ""),
                "source": str(item.get("source") or ""),
                "firstSeen": item.get("firstSeen"),
                "lastSeen": item.get("lastSeen"),
                "lastMissingAt": item.get("lastMissingAt"),
                "active": item.get("active") is True,
            })

    source_health = []
    discovery = refresh.get("newGameDiscovery") if isinstance(refresh, dict) else {}
    raw_source_health = discovery.get("sourceResults") if isinstance(discovery, dict) else []
    for item in raw_source_health or []:
        if not isinstance(item, dict):
            continue
        source_health.append({
            "source": str(item.get("source") or ""),
            "sourceLabel": str(item.get("sourceLabel") or item.get("source") or ""),
            "scope": str(item.get("scope") or "unspecified"),
            "listingPagesAttempted": int(item.get("listingPagesAttempted") or 0),
            "fetchErrors": int(item.get("fetchErrors") or 0),
            "candidateCount": int(item.get("candidateCount") or 0),
            "scanComplete": item.get("scanComplete") is True,
            "catalogComplete": item.get("catalogComplete") is True,
            "candidateLimitReached": item.get("candidateLimitReached") is True,
        })

    return {
        "phase": "PUBLIC_NEW_GAME_MONITOR_V1",
        "checkedAt": queue.get("checkedAt") if isinstance(queue, dict) else None,
        "candidateOnly": True,
        "publicationAuthorized": False,
        "items": candidates,
        "reviewPriority": priority,
        "historyItems": history_items,
        "sourceHealth": source_health,
    }


def _build_existing_game_monitor_snapshot() -> dict:
    queue = _load_optional_json(ROOT / "data" / "existing_game_candidate_queue.json", {})
    raw_items = queue.get("items") if isinstance(queue, dict) else []
    items = []
    for item in raw_items or []:
        if not isinstance(item, dict):
            continue
        items.append({
            "game": str(item.get("game") or ""),
            "source": str(item.get("source") or ""),
            "url": _safe_monitor_url(item.get("url")),
            "offerIdentity": str(item.get("offerIdentity") or ""),
            "reason": str(item.get("reason") or ""),
            "storedReward": item.get("storedReward"),
            "detectedReward": item.get("detectedReward"),
            "platformHint": str(item.get("platformHint") or ""),
            "parserVersion": str(item.get("parserVersion") or ""),
            "checkedAt": str(item.get("checkedAt") or ""),
        })
    return {
        "phase": "PUBLIC_EXISTING_GAME_MONITOR_V1",
        "checkedAt": queue.get("checkedAt") if isinstance(queue, dict) else None,
        "candidateOnly": True,
        "publicationAuthorized": False,
        "count": len(items),
        "rewardChangeCount": sum(
            1 for item in items
            if item["reason"] in {
                "reward_change_candidate",
                "moppy_shell_reward_change_candidate",
                "first_party_existing_game_reward_change_candidate",
            }
        ),
        "newOfferCount": sum(
            1 for item in items
            if item["reason"] == "first_party_existing_game_new_offer_candidate"
        ),
        "verifiedSameRewardCount": sum(
            1 for item in items
            if item["reason"] == "first_party_existing_game_reward_verified"
        ),
        "items": items,
    }


def _write_or_copy_monitor(source_name: str, destination: Path, builder) -> None:
    source = ROOT / "data" / source_name
    if source.exists() and not source.is_symlink():
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and str(payload.get("phase") or "").startswith("PUBLIC_"):
            _copy_file(source, destination)
            return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(builder(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_public_site(output: Path) -> list[str]:
    output = output.resolve()
    if output == ROOT or ROOT not in output.parents:
        raise ValueError("unsafe_output_directory")

    if output.exists():
        if output.is_symlink():
            raise ValueError("symlink_output_rejected")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for name in ROOT_FILES:
        _copy_file(ROOT / name, output / name)

    for name in DATA_FILES:
        _copy_file(ROOT / "data" / name, output / "data" / name)

    for name in CONFIG_FILES:
        _copy_file(ROOT / "config" / name, output / "config" / name)

    _write_or_copy_monitor(
        "new_game_monitor.json",
        output / "data" / "new_game_monitor.json",
        _build_new_game_monitor_snapshot,
    )
    _write_or_copy_monitor(
        "existing_game_monitor.json",
        output / "data" / "existing_game_monitor.json",
        _build_existing_game_monitor_snapshot,
    )

    for name in DATA_DIRS:
        _copy_tree(ROOT / "data" / name, output / "data" / name)

    for name in PUBLIC_DIRS:
        _copy_tree(ROOT / name, output / name)

    copied = sorted(
        str(path.relative_to(output)).replace("\\", "/")
        for path in output.rglob("*")
        if path.is_file()
    )
    return copied


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the explicit POIGAME LAB public-site artifact."
    )
    parser.add_argument(
        "--output",
        default="_site",
        help="Disposable output directory beneath the repository root (default: _site).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    output = (ROOT / args.output).resolve()
    copied = build_public_site(output)
    print(f"Built {len(copied)} public files in {output.relative_to(ROOT)}")
    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
