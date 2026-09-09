import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_refresh_module():
    spec = importlib.util.spec_from_file_location(
        "direct_offer_refresh", ROOT / "scripts" / "direct_offer_refresh.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reappearing_candidate_keeps_original_first_seen():
    direct = load_refresh_module()
    key = "amefuri|amefuri:pathid:123"
    previous = {
        "items": {
            key: {
                "source": "amefuri",
                "offerIdentity": "amefuri:pathid:123",
                "titleHint": "新作RPG",
                "firstPartyCandidateUrl": "https://www.amefri.net/detail/id/123",
                "firstSeen": "2026-09-08T01:00:00+09:00",
                "lastSeen": "2026-09-08T01:00:00+09:00",
                "seenCount": 1,
                "active": False,
                "isNewToday": False,
                "lastMissingAt": "2026-09-09T01:00:00+09:00",
            }
        }
    }
    current = [{
        "source": "amefuri",
        "offerIdentity": "amefuri:pathid:123",
        "titleHint": "新作RPG",
        "firstPartyCandidateUrl": "https://www.amefri.net/detail/id/123",
    }]
    result = direct.build_new_game_history(current, previous, "2026-09-10T01:00:00+09:00")
    item = result["items"][key]
    assert item["firstSeen"] == "2026-09-08T01:00:00+09:00"
    assert item["isNewToday"] is False
    assert item["active"] is True
    assert item["seenCount"] == 2
