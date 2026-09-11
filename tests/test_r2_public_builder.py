import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_public_site", ROOT / "scripts" / "build_public_site.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_public_build_emits_compact_monitor_snapshots(tmp_path):
    output = ROOT / ".test-r2-public-build"
    copied = set(builder.build_public_site(output))
    try:
        assert "data/new_game_monitor.json" in copied
        assert "data/existing_game_monitor.json" in copied
        assert "data/new_game_candidate_queue.json" not in copied
        assert "data/new_game_candidate_history.json" not in copied
        assert "data/existing_game_candidate_queue.json" not in copied
        assert "data/comparison_candidate_queue.json" not in copied
        assert "data/comparison_review_queue.json" not in copied
        assert "data/comparison_refresh_status.json" not in copied

        new_monitor = json.loads((output / "data" / "new_game_monitor.json").read_text(encoding="utf-8"))
        existing_monitor = json.loads((output / "data" / "existing_game_monitor.json").read_text(encoding="utf-8"))
        assert new_monitor["phase"] == "PUBLIC_NEW_GAME_MONITOR_V1"
        assert existing_monitor["phase"] == "PUBLIC_EXISTING_GAME_MONITOR_V1"
        assert new_monitor["publicationAuthorized"] is False
        assert existing_monitor["publicationAuthorized"] is False
    finally:
        if output.exists():
            import shutil
            shutil.rmtree(output)
