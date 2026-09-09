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


def test_first_seen_is_stable_and_only_first_run_is_new_today():
    direct = load_refresh_module()
    current = [{
        "source": "amefuri",
        "offerIdentity": "amefuri:pathid:123",
        "titleHint": "新作RPG",
        "firstPartyCandidateUrl": "https://www.amefri.net/detail/id/123",
    }]
    first = direct.build_new_game_history(current, {"items": {}}, "2026-09-09T01:00:00+09:00")
    item = next(iter(first["items"].values()))
    assert item["firstSeen"] == "2026-09-09T01:00:00+09:00"
    assert item["isNewToday"] is True
    assert item["seenCount"] == 1

    second = direct.build_new_game_history(current, first, "2026-09-10T01:00:00+09:00")
    item2 = next(iter(second["items"].values()))
    assert item2["firstSeen"] == "2026-09-09T01:00:00+09:00"
    assert item2["isNewToday"] is False
    assert item2["seenCount"] == 2


def test_missing_candidate_is_retained_as_inactive_history():
    direct = load_refresh_module()
    previous = {
        "items": {
            "amefuri|amefuri:pathid:123": {
                "source": "amefuri",
                "offerIdentity": "amefuri:pathid:123",
                "titleHint": "新作RPG",
                "firstSeen": "2026-09-09T01:00:00+09:00",
                "lastSeen": "2026-09-09T01:00:00+09:00",
                "seenCount": 1,
                "active": True,
            }
        }
    }
    result = direct.build_new_game_history([], previous, "2026-09-10T01:00:00+09:00")
    item = result["items"]["amefuri|amefuri:pathid:123"]
    assert item["active"] is False
    assert item["isNewToday"] is False
    assert item["lastMissingAt"] == "2026-09-10T01:00:00+09:00"


def test_history_never_authorizes_auto_create_or_publication():
    direct = load_refresh_module()
    current = [{
        "source": "ec_navi",
        "offerIdentity": "ec_navi:pathid:999",
        "titleHint": "新作ゲーム",
        "firstPartyCandidateUrl": "https://ecnavi.jp/ad/999/show/",
    }]
    result = direct.build_new_game_history(current, {"items": {}}, "2026-09-09T01:00:00+09:00")
    item = next(iter(result["items"].values()))
    assert item["candidateOnly"] is True
    assert item["autoCreateAuthorized"] is False
    assert item["publicationAuthorized"] is False
