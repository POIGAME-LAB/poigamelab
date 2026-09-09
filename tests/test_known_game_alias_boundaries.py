from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def load_refresh_module():
    spec = importlib.util.spec_from_file_location(
        "direct_offer_refresh", ROOT / "scripts" / "direct_offer_refresh.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_known_title_with_subtitle_is_suppressed_but_similar_title_is_not():
    direct = load_refresh_module()
    targets = [{"game": "放置少女", "aliases": ["放置少女〜百花繚乱の萌姫たち〜"]}]
    assert direct.context_matches_known_game("放置少女 ～百花繚乱の萌姫たち～ Lv120到達", targets) is True
    assert direct.context_matches_known_game("放置勇者 新作RPG", targets) is False
