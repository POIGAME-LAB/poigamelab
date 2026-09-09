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


def test_new_game_title_clustering_only_normalizes_explicit_os_decorations():
    direct = load_refresh_module()
    assert direct.new_game_title_cluster_key("iOS_新作ゲーム") == direct.new_game_title_cluster_key("新作ゲーム（iOS）")
    assert direct.new_game_title_cluster_key("And_新作ゲーム") == direct.new_game_title_cluster_key("新作ゲーム")
    assert direct.new_game_title_cluster_key("新作ゲーム2") != direct.new_game_title_cluster_key("新作ゲーム")


def test_multi_source_cluster_is_review_only_and_ranked_first():
    direct = load_refresh_module()
    items = [
        {"source": "amefuri", "titleHint": "iOS_新作ゲーム"},
        {"source": "ec_navi", "titleHint": "新作ゲーム（iOS）"},
        {"source": "powl", "titleHint": "別ゲーム"},
    ]
    clusters = direct.build_new_game_candidate_clusters(items)
    first = clusters[0]
    assert first["sourceCount"] == 2
    assert first["candidateCount"] == 2
    assert set(first["sources"]) == {"amefuri", "ec_navi"}
    assert first["reviewOnly"] is True
    assert first["identityAuthorized"] is False
    assert first["autoCreateAuthorized"] is False
    assert first["publicationAuthorized"] is False


def test_queue_payload_persists_clusters_without_replacing_raw_items():
    refresh = (ROOT / "scripts" / "direct_offer_refresh.py").read_text(encoding="utf-8")
    assert '"clusterCount": len(new_game_clusters)' in refresh
    assert '"clusters": new_game_clusters' in refresh
    assert '"items": new_game_candidate_queue' in refresh
