import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_scan_review as daily


def coincome_source():
    return {"id": "coincome", "search_domains": ["cimcome.jp"], "mobile": True}


def amefuri_source():
    return {"id": "amefuri", "search_domains": ["www.amefri.net", "amefri.net"], "mobile": True}


def moppy_source():
    return {"id": "moppy", "search_domains": ["moppy.jp", "pc.moppy.jp"], "mobile": False}


def test_coincome_empty_listing_retries_once_then_accepts_detail_links():
    calls = []
    responses = [
        ("<html>temporary empty edge response</html>", "https://cimcome.jp/campaigns?_category_id=21"),
        ('<a href="/campaigns/details/123">Game</a>', "https://cimcome.jp/campaigns?_category_id=21"),
    ]

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append((url, source["id"], timeout, max_bytes))
        return responses.pop(0)

    raw, final_url = daily.resilient_fetch_first_party(
        "https://cimcome.jp/campaigns?_category_id=21",
        coincome_source(),
        base_fetch=fake,
    )

    assert len(calls) == 2
    assert "/campaigns/details/123" in raw
    assert final_url == "https://cimcome.jp/campaigns?_category_id=21"


def test_coincome_two_empty_listings_fail_closed():
    calls = []

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append(url)
        return "<html>still empty</html>", url

    with pytest.raises(ValueError, match="coincome app listing missing detail identities after retry"):
        daily.resilient_fetch_first_party(
            "https://cimcome.jp/campaigns?_category_id=21",
            coincome_source(),
            base_fetch=fake,
        )

    assert len(calls) == 2


def test_coincome_normal_listing_is_fetched_once():
    calls = []

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append(url)
        return '<a href="/campaigns/details/1">Game</a>', url

    raw, _ = daily.resilient_fetch_first_party(
        "https://cimcome.jp/campaigns?_category_id=21",
        coincome_source(),
        base_fetch=fake,
    )

    assert len(calls) == 1
    assert "/campaigns/details/1" in raw


def test_amefuri_transient_timeout_retries_once():
    calls = []

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError()
        return "", url

    raw, final_url = daily.resilient_fetch_first_party(
        "https://www.amefri.net/item_list?page=21&slug=app_game",
        amefuri_source(),
        base_fetch=fake,
    )

    assert raw == ""
    assert final_url.endswith("page=21&slug=app_game")
    assert len(calls) == 2


def test_amefuri_empty_success_does_not_retry():
    calls = []

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append(url)
        return "", url

    raw, _ = daily.resilient_fetch_first_party(
        "https://www.amefri.net/item_list?page=26&slug=app_game",
        amefuri_source(),
        base_fetch=fake,
    )

    assert raw == ""
    assert len(calls) == 1


def test_non_target_listing_does_not_retry_transport_error():
    calls = []
    source = {"id": "warau", "search_domains": ["www.warau.jp"], "mobile": True}

    def fake(url, source, timeout=15, max_bytes=1200000):
        calls.append(url)
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        daily.resilient_fetch_first_party(
            "https://www.warau.jp/contents/point/category?point_group=2",
            source,
            base_fetch=fake,
        )

    assert len(calls) == 1


def test_moppy_ajax_uses_only_required_xrw_header():
    ajax_url = (
        "https://pc.moppy.jp/ajax/category/get_list.php?parent_category=4&child_category=52"
        "&objective_category=&current_page=1&af_sorter=1&exclude_purchased="
    )
    captured = {}

    class Headers:
        @staticmethod
        def get_content_charset():
            return "utf-8"

    class Response:
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def geturl():
            return ajax_url

        @staticmethod
        def read(_limit):
            return b"<div>fixture</div>"

    class Opener:
        @staticmethod
        def open(request, timeout=15):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    def opener_factory(*handlers):
        captured["handlers"] = handlers
        return Opener()

    raw, final_url = daily._fetch_moppy_ajax(
        ajax_url,
        moppy_source(),
        opener_factory=opener_factory,
    )

    headers = {key.lower(): value for key, value in captured["request"].header_items()}
    assert raw == "<div>fixture</div>"
    assert final_url == ajax_url
    assert headers["x-requested-with"] == "XMLHttpRequest"
    assert "referer" not in headers
    assert "POIGAMELAB/1.0" in headers["user-agent"]
    assert captured["timeout"] == 15
