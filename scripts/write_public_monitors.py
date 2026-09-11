#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from build_public_site import (
    ROOT,
    _build_existing_game_monitor_snapshot,
    _build_new_game_monitor_snapshot,
)

MAX_TODAY_ITEMS = 100
MAX_CONTINUING_ITEMS = 200
MAX_PRIORITY_ITEMS = 100
MAX_INACTIVE_ITEMS = 100
MAX_EXISTING_ITEMS = 200


def _compact_new_game_monitor(payload: dict) -> dict:
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    priority = [item for item in payload.get("reviewPriority", []) if isinstance(item, dict)]
    history = [item for item in payload.get("historyItems", []) if isinstance(item, dict)]

    today = [item for item in items if item.get("isNewToday") is True]
    continuing = [item for item in items if item.get("isNewToday") is not True]
    high = [item for item in priority if item.get("reviewPriority") == "high"]
    inactive = [item for item in history if item.get("active") is False]
    inactive.sort(key=lambda item: str(item.get("lastMissingAt") or ""), reverse=True)

    compact_items = today[:MAX_TODAY_ITEMS] + continuing[:MAX_CONTINUING_ITEMS]
    compact = dict(payload)
    compact["counts"] = {
        "new": len(today),
        "active": len(items),
        "highPriority": len(high),
        "inactive": len(inactive),
    }
    compact["displayLimits"] = {
        "today": MAX_TODAY_ITEMS,
        "continuing": MAX_CONTINUING_ITEMS,
        "priority": MAX_PRIORITY_ITEMS,
        "inactive": MAX_INACTIVE_ITEMS,
    }
    compact["items"] = compact_items
    compact["reviewPriority"] = high[:MAX_PRIORITY_ITEMS]
    compact["historyItems"] = inactive[:MAX_INACTIVE_ITEMS]
    return compact


def _compact_existing_game_monitor(payload: dict) -> dict:
    compact = dict(payload)
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    compact["displayLimit"] = MAX_EXISTING_ITEMS
    compact["items"] = items[:MAX_EXISTING_ITEMS]
    return compact


def write_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(path)


def main() -> int:
    new_payload = _compact_new_game_monitor(_build_new_game_monitor_snapshot())
    existing_payload = _compact_existing_game_monitor(_build_existing_game_monitor_snapshot())
    write_snapshot(ROOT / "data" / "new_game_monitor.json", new_payload)
    write_snapshot(ROOT / "data" / "existing_game_monitor.json", existing_payload)
    print(
        "Wrote bounded public monitor snapshots "
        f"(new items={len(new_payload['items'])}, "
        f"priority={len(new_payload['reviewPriority'])}, "
        f"inactive={len(new_payload['historyItems'])}, "
        f"existing={len(existing_payload['items'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
