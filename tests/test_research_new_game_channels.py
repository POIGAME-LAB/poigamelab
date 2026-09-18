import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_new_game_channels as r


def queue():
    return {
        "phase": "NEW_GAME_CONTENT_QUEUE_V1",
        "items": [{
            "rank": 1,
            "game": "新作ゲーム",
            "maxObservedRewardYen": 12345,
            "pointSiteEvidence": [
                {"source": "warau", "url": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=1"},
                {"source": "amefuri", "url": "https://www.amefri.net/detail/id/2"},
            ],
            "researchQueries": {
                "web": "新作ゲーム ポイ活 攻略",
                "x": "site:x.com 新作ゲーム ポイ活",
                "youtube": "site:youtube.com 新作ゲーム ポイ活",
                "instagram": "site:instagram.com 新作ゲーム ポイ活",
                "pointSites": "新作ゲーム ポイ活 口コミ",
            },
        }],
    }


def searcher(query, key, max_results):
    if "x.com" in query:
        url = "https://x.com/user/status/123"
    elif "youtube.com" in query:
        url = "https://www.youtube.com/watch?v=abc"
    elif "instagram.com" in query:
        url = "https://www.instagram.com/p/abc/"
    else:
        url = "https://example.com/new-game-guide"
    return {"results": [{"url": url}]}


def fetcher(url):
    return "新作ゲーム のポイ活案件を10日で達成。レベル20まで進めた記録。", {"httpStatus": 200}


class TestResearchNewGameChannels(unittest.TestCase):
    def test_researches_all_channels_without_publication(self):
        item = queue()["items"][0]
        out = r.research_item(item, "dummy", searcher=searcher, fetcher=fetcher)
        self.assertTrue(out["complete"])
        self.assertFalse(out["publicationAuthorized"])
        self.assertEqual(out["apiCalls"], 4)
        self.assertEqual(set(out["research"]), {"web", "x", "youtube", "instagram", "pointSites"})
        self.assertEqual(len(out["research"]["pointSites"]["sources"]), 2)
        for channel in ("web", "x", "youtube", "instagram"):
            self.assertTrue(out["research"][channel]["complete"])
            self.assertTrue(out["research"][channel]["sources"][0]["targetConfirmed"])

    def test_one_point_site_is_enough_to_begin_quarantined_research(self):
        item = queue()["items"][0]
        item["pointSiteEvidence"] = item["pointSiteEvidence"][:1]
        out = r.research_item(item, "dummy", searcher=searcher, fetcher=fetcher)
        self.assertTrue(out["complete"])
        self.assertEqual(len(out["research"]["pointSites"]["sources"]), 1)
        self.assertFalse(out["publicationAuthorized"])

    def test_search_error_is_visible_and_incomplete(self):
        def broken(query, key, max_results):
            raise RuntimeError("nope")
        lane = r.research_channel("新作ゲーム", "web", "q", "dummy", searcher=broken, fetcher=fetcher)
        self.assertTrue(lane["searched"])
        self.assertFalse(lane["complete"])
        self.assertEqual(lane["searchErrors"], 1)
        self.assertEqual(lane["sources"], [])

    def test_snippet_only_never_becomes_source(self):
        def search(query, key, max_results):
            return {"results": [{"url": "https://example.com/x", "content": "新作ゲーム 7日達成"}]}
        def other_page(url):
            return "まったく別のゲーム", {"httpStatus": 200}
        lane = r.research_channel("新作ゲーム", "web", "q", "dummy", searcher=search, fetcher=other_page)
        self.assertTrue(lane["complete"])
        self.assertEqual(lane["sources"], [])

    def test_social_domain_filter_rejects_wrong_host(self):
        def search(query, key, max_results):
            return {"results": [{"url": "https://example.com/fake-x"}]}
        lane = r.research_channel("新作ゲーム", "x", "q", "dummy", searcher=search, fetcher=fetcher)
        self.assertTrue(lane["complete"])
        self.assertEqual(lane["directFetches"], 0)
        self.assertEqual(lane["sources"], [])

    def test_run_writes_quarantine_artifact_only(self):
        with tempfile.TemporaryDirectory() as td:
            old_status = r.STATUS
            r.STATUS = Path(td) / "status.json"
            try:
                status = r.run(queue=queue(), api_key="dummy", searcher=searcher, fetcher=fetcher,
                               out_dir=Path(td) / "research")
                self.assertTrue(status["success"])
                self.assertEqual(status["games"], 1)
                self.assertEqual(status["publicationWrites"], 0)
                files = list((Path(td) / "research").glob("*.json"))
                self.assertEqual(len(files), 1)
                payload = json.loads(files[0].read_text())
                self.assertFalse(payload["publicationAuthorized"])
            finally:
                r.STATUS = old_status


if __name__ == "__main__":
    unittest.main()
