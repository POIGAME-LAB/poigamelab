"""Manual read-only capture of first-party pages for parser fixes (network mocked)."""
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import capture_offer_pages as cap  # noqa: E402

SOURCES = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}


def test_plan_only_registered_hosts_deduplicated_and_bounded():
    targets = [
        {"game": "A", "known_urls_by_source": {"hapitas": ["https://hapitas.jp/item/detail/itemid/1", "https://hapitas.jp/item/detail/itemid/1",
                                                           "https://evil.example/item/2"], "warau": ["https://www.warau.jp/contents/point/pointEntrance.php?point_id=3"]}},
    ]
    items = cap.plan(SOURCES, targets, ("hapitas",), max_pages=500)
    urls = [i["url"] for i in items]
    assert "https://hapitas.jp/item/detail/itemid/1" in urls and urls.count("https://hapitas.jp/item/detail/itemid/1") == 1
    assert not any("evil.example" in u or "warau" in u for u in urls)
    assert len(cap.plan(SOURCES, targets * 200, ("hapitas", "warau"), max_pages=9999)) <= cap.MAX_PAGES


def test_capture_records_pages_errors_and_parser_verdicts(tmp_path):
    items = [
        {"source": "nifty_point", "url": "https://api.point.nifty.com/service/alist/spapp", "kind": "listing", "game": ""},
        {"source": "moppy", "url": "https://pc.moppy.jp/ad/detail.php?site_id=1", "kind": "detail", "game": "テスト"},
    ]

    def fetcher(url, source):
        if "nifty" in url:
            raise HTTPError(url, 404, "Not Found", {}, None)
        return "<html><h1>x</h1></html>", url

    index = cap.capture(items, tmp_path, SOURCES, {"テスト": ["テスト"]}, fetcher=fetcher, delay=0)
    assert index[0]["status"] == "http_status_404"
    assert index[1]["status"] == "ok" and (tmp_path / index[1]["file"]).read_text(encoding="utf-8").startswith("<html>")
    assert index[1]["parser"]["state"] == "review_required"
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))[0]["source"] == "nifty_point"


def test_workflow_is_manual_read_only_and_secret_free():
    text = (ROOT / ".github/workflows/capture-offer-pages.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "schedule:" not in text and "workflow_run:" not in text
    assert "contents: read" in text and "contents: write" not in text and "git push" not in text
    assert "secrets." not in text and "API_KEY" not in text
    assert "retention-days: 3" in text
