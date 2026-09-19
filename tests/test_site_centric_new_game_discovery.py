import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_refresh_module():
    spec = importlib.util.spec_from_file_location(
        "direct_offer_refresh", ROOT / "scripts" / "direct_offer_refresh.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_game_discovery_is_candidate_only_and_suppresses_known_games():
    direct = load_refresh_module()
    source = {
        "id": "amefuri",
        "name": "アメフリ",
        "search_domains": ["www.amefri.net", "amefri.net"],
        "direct_detail_url_hints": ["/detail/id/"],
    }
    targets = [
        {
            "game": "Township",
            "aliases": ["Township", "タウンシップ"],
            "known_urls_by_source": {
                "amefuri": ["https://www.amefri.net/detail/id/111"]
            },
        }
    ]
    raw = """
    <ul>
      <li class="item-card">
        <a href="/detail/id/111">Township</a>
      </li>
      <li class="item-card">
        <a href="/detail/id/222">新作ゲームXYZ</a>
      </li>
    </ul>
    """
    items = direct.discover_new_game_listing_candidates(
        raw, "https://www.amefri.net/item_list?slug=app_game",
        source, targets, limit=20
    )
    assert len(items) == 1
    item = items[0]
    assert item["titleHint"] == "新作ゲームXYZ"
    assert item["firstPartyCandidateUrl"] == "https://www.amefri.net/detail/id/222"
    assert item["candidateOnly"] is True
    assert item["firstPartyVerificationRequired"] is True
    assert item["autoCreateAuthorized"] is False
    assert item["publicationAuthorized"] is False


def test_hapitas_candidate_title_excludes_reward_caption():
    direct = load_refresh_module()
    source = {
        "id": "hapitas",
        "name": "ハピタス",
        "search_domains": ["hapitas.jp"],
        "direct_detail_url_hints": ["/item/detail/itemid/"],
    }
    raw = '''
    <div class="item_slots_thumb">
      <a href="https://hapitas.jp/item/detail/itemid/98600/apn/navigation_category" class="thumb_slots_link">
        <div class="thumb-inner">
          <div class="thumb_slots_title"><p class="store">パズル＆コンクエスト</p></div>
          <p class="caption">26,172pt</p>
        </div>
      </a>
    </div>
    '''
    items = direct.discover_new_game_listing_candidates(
        raw, "https://hapitas.jp/category/service_app/apn/navigation_category/",
        source, [], limit=20
    )
    assert len(items) == 1
    assert items[0]["titleHint"] == "パズル＆コンクエスト"
    assert "26,172" not in items[0]["titleHint"]


def test_hapitas_known_game_is_still_suppressed_with_reward_caption():
    direct = load_refresh_module()
    source = {
        "id": "hapitas",
        "name": "ハピタス",
        "search_domains": ["hapitas.jp"],
        "direct_detail_url_hints": ["/item/detail/itemid/"],
    }
    targets = [{
        "game": "パズル＆サバイバル",
        "aliases": ["パズル＆サバイバル", "パズル&サバイバル"],
        "known_urls_by_source": {},
    }]
    raw = '''
    <div class="item_slots_thumb">
      <a href="https://hapitas.jp/item/detail/itemid/98148/apn/navigation_category" class="thumb_slots_link">
        <div class="thumb-inner">
          <div class="thumb_slots_title"><p class="store">パズル＆サバイバル</p></div>
          <p class="caption">34,861pt</p>
        </div>
      </a>
    </div>
    '''
    items = direct.discover_new_game_listing_candidates(
        raw, "https://hapitas.jp/category/service_app/apn/navigation_category/",
        source, targets, limit=20
    )
    assert items == []

def test_amefuri_is_first_site_centric_new_game_source():
    cfg = json.loads((ROOT / "config" / "point_sources.json").read_text(encoding="utf-8"))
    source = next(x for x in cfg["sources"] if x["id"] == "amefuri")
    assert source["full_catalog_discovery_enabled"] is True
    assert source["new_game_discovery_enabled"] is True
    assert source["new_game_discovery_listing_limit"] == 26
    assert len(source["direct_listing_urls"]) == 26


def test_nightly_workflow_persists_new_game_queue_at_1am_jst():
    workflow = (ROOT / ".github" / "workflows" / "refresh-verified-offers.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "17 16 * * *"' in workflow
    assert "data/new_game_candidate_queue.json" in workflow
    assert "git add data/new_game_candidate_queue.json" in workflow


def test_new_game_queue_never_auto_creates_or_publishes():
    refresh = (ROOT / "scripts" / "direct_offer_refresh.py").read_text(encoding="utf-8")
    assert '"autoCreateAuthorized": False' in refresh
    assert '"publicationAuthorized": False' in refresh
    assert "DIRECT_NEW_GAME_CANDIDATE_QUEUE_V1" in refresh
