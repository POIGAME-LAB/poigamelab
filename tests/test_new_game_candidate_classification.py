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


def test_game_candidate_classifier_prioritizes_obvious_game_titles():
    direct = load_refresh_module()
    result = direct.classify_new_game_candidate(
        {"titleHint": "新作放置RPG レベル80到達"}
    )
    assert result["classification"] == "likely_game"
    assert result["classificationScore"] >= 2
    assert result["classificationReviewOnly"] is True
    assert result["classificationAuthorized"] is False


def test_game_candidate_classifier_flags_obvious_non_game_titles():
    direct = load_refresh_module()
    result = direct.classify_new_game_candidate(
        {"titleHint": "クレジットカード発行でポイント"}
    )
    assert result["classification"] == "likely_non_game"
    assert result["classificationScore"] <= -2


def test_ambiguous_titles_are_preserved_for_review():
    direct = load_refresh_module()
    result = direct.classify_new_game_candidate(
        {"titleHint": "新サービスXYZ"}
    )
    assert result["classification"] == "review"


def test_classifier_never_deletes_or_authorizes_candidates():
    refresh = (ROOT / "scripts" / "direct_offer_refresh.py").read_text(encoding="utf-8")
    assert "candidate.update(classify_new_game_candidate(candidate))" in refresh
    assert '"classificationReviewOnly": True' in refresh
    assert '"classificationAuthorized": False' in refresh
    assert '"items": new_game_candidate_queue' in refresh
