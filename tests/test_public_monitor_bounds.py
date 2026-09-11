import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "write_public_monitors", ROOT / "scripts" / "write_public_monitors.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_new_game_monitor_is_bounded_but_keeps_true_counts():
    payload = {
        "phase": "PUBLIC_NEW_GAME_MONITOR_V1",
        "items": [
            {"titleHint": f"new-{i}", "isNewToday": True}
            for i in range(module.MAX_TODAY_ITEMS + 25)
        ] + [
            {"titleHint": f"old-{i}", "isNewToday": False}
            for i in range(module.MAX_CONTINUING_ITEMS + 25)
        ],
        "reviewPriority": [
            {"titleHint": f"high-{i}", "reviewPriority": "high"}
            for i in range(module.MAX_PRIORITY_ITEMS + 25)
        ],
        "historyItems": [
            {"titleHint": f"inactive-{i}", "active": False, "lastMissingAt": f"2026-09-{(i % 28) + 1:02d}"}
            for i in range(module.MAX_INACTIVE_ITEMS + 25)
        ],
        "sourceHealth": [],
    }

    compact = module._compact_new_game_monitor(payload)

    assert compact["counts"] == {
        "new": module.MAX_TODAY_ITEMS + 25,
        "active": module.MAX_TODAY_ITEMS + module.MAX_CONTINUING_ITEMS + 50,
        "highPriority": module.MAX_PRIORITY_ITEMS + 25,
        "inactive": module.MAX_INACTIVE_ITEMS + 25,
    }
    assert len(compact["items"]) == module.MAX_TODAY_ITEMS + module.MAX_CONTINUING_ITEMS
    assert len(compact["reviewPriority"]) == module.MAX_PRIORITY_ITEMS
    assert len(compact["historyItems"]) == module.MAX_INACTIVE_ITEMS


def test_existing_game_monitor_is_bounded():
    payload = {
        "phase": "PUBLIC_EXISTING_GAME_MONITOR_V1",
        "count": module.MAX_EXISTING_ITEMS + 25,
        "items": [{"game": f"game-{i}"} for i in range(module.MAX_EXISTING_ITEMS + 25)],
    }
    compact = module._compact_existing_game_monitor(payload)
    assert compact["count"] == module.MAX_EXISTING_ITEMS + 25
    assert len(compact["items"]) == module.MAX_EXISTING_ITEMS
