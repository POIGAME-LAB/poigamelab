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


def test_normalized_game_title_key_absorbs_safe_presentation_variants():
    direct = load_refresh_module()
    assert direct.normalized_game_title_key("パズル＆サバイバル") == direct.normalized_game_title_key("パズル & サバイバル")
    assert direct.normalized_game_title_key("iOS_キングショット") == direct.normalized_game_title_key("キングショット（iOS）")


def test_context_matches_known_game_by_alias_and_normalized_key():
    direct = load_refresh_module()
    targets = [
        {
            "game": "パズル＆サバイバル",
            "aliases": ["パズル&サバイバル", "Puzzles & Survival"],
        }
    ]
    assert direct.context_matches_known_game("Puzzles&Survival レベル30到達", targets) is True
    assert direct.context_matches_known_game("パズル・サバイバル", targets) is True
    assert direct.context_matches_known_game("まったく別の新作RPG", targets) is False


def test_new_game_discovery_suppresses_normalized_known_title_variant():
    direct = load_refresh_module()
    source = {
        "id": "amefuri",
        "name": "アメフリ",
        "search_domains": ["www.amefri.net", "amefri.net"],
        "direct_detail_url_hints": ["/detail/id/"],
    }
    targets = [
        {
            "game": "パズル＆サバイバル",
            "aliases": ["Puzzles & Survival"],
            "known_urls_by_source": {},
        }
    ]
    raw = """
    <ul>
      <li class="item-card"><a href="/detail/id/321">パズル・サバイバル</a></li>
      <li class="item-card"><a href="/detail/id/654">完全新作ゲーム</a></li>
    </ul>
    """
    items = direct.discover_new_game_listing_candidates(
        raw, "https://www.amefri.net/item_list?slug=app_game", source, targets, limit=10
    )
    assert len(items) == 1
    assert items[0]["titleHint"] == "完全新作ゲーム"
