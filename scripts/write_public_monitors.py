#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from build_public_site import (
    ROOT,
    _build_existing_game_monitor_snapshot,
    _build_new_game_monitor_snapshot,
)


def write_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    write_snapshot(ROOT / "data" / "new_game_monitor.json", _build_new_game_monitor_snapshot())
    write_snapshot(ROOT / "data" / "existing_game_monitor.json", _build_existing_game_monitor_snapshot())
    print("Wrote compact public monitor snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
