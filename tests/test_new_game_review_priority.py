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


def test_multi_source_likely_game_ranks_above_single_source_review():
    direct = load_refresh_module()
    items = [
        {"source": "amefuri", "titleHint": "新作RPG", "classification": "likely_game"},
        {"source": "ec_navi", "titleHint": "新作RPG（iOS）", "classification": "likely_game"},
        {"source": "powl", "titleHint": "未知サービス", "classification": "review"},
    ]
    clusters = direct.build_new_game_candidate_clusters(items)
    ranked = direct.build_new_game_review_priority(items, clusters)
    assert ranked[0]["reviewPriority"] == "high"
    assert ranked[0]["sourceCount"] == 2
    assert ranked[0]["reviewPriorityScore"] > ranked[-1]["reviewPriorityScore"]


def test_likely_non_game_stays_low_even_when_preserved():
    direct = load_refresh_module()
    items = [
        {"source": "amefuri", "titleHint": "クレジットカード発行", "classification": "likely_non_game"}
    ]
    clusters = direct.build_new_game_candidate_clusters(items)
    ranked = direct.build_new_game_review_priority(items, clusters)
    assert ranked[0]["reviewPriority"] == "low"
    assert ranked[0]["reviewOnly"] is True
    assert ranked[0]["autoCreateAuthorized"] is False
    assert ranked[0]["publicationAuthorized"] is False


def test_priority_is_persisted_without_replacing_raw_candidates():
    refresh = (ROOT / "scripts" / "direct_offer_refresh.py").read_text(encoding="utf-8")
    assert '"reviewPriority": new_game_review_priority' in refresh
    assert '"items": new_game_candidate_queue' in refresh
