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

    def test_point_site_lane_uses_unique_ids_for_multiple_offers_from_one_site(self):
        item = {
            "pointSiteEvidence": [
                {"source": "hapitas", "url": "https://hapitas.jp/item/detail/itemid/100/"},
                {"source": "hapitas", "url": "https://hapitas.jp/item/detail/itemid/101/"},
                {"source": "amefuri", "url": "https://www.amefri.net/detail/id/200"},
            ]
        }
        lane = r.point_site_lane(item)
        ids = [row["id"] for row in lane["sources"]]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(sum(x.startswith("pointSites:hapitas:") for x in ids), 2)
        self.assertTrue(any(x.startswith("pointSites:amefuri:") for x in ids))

    def test_multiple_offers_from_only_one_site_do_not_satisfy_two_site_gate(self):
        item = {
            "pointSiteEvidence": [
                {"source": "hapitas", "url": "https://hapitas.jp/item/detail/itemid/100/"},
                {"source": "hapitas", "url": "https://hapitas.jp/item/detail/itemid/101/"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "point_site_evidence_below_two"):
            r.point_site_lane(item)

    def test_search_error_is_visible_and_incomplete(self):
        def broken(query, key, max_results):
            raise RuntimeError("nope")
        lane = r.research_channel(
            "新作ゲーム", "web", "q", "dummy",
            searcher=broken, fetcher=fetcher, sleeper=lambda _: None,
        )
        self.assertTrue(lane["searched"])
        self.assertFalse(lane["complete"])
        self.assertEqual(lane["searchCalls"], 2)
        self.assertEqual(lane["searchErrors"], 2)
        self.assertEqual(lane["sources"], [])

    def test_transient_search_error_recovers_on_one_bounded_retry(self):
        calls = {"count": 0}
        def flaky(query, key, max_results):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary")
            return {"results": [{"url": "https://example.com/new-game-guide"}]}

        lane = r.research_channel(
            "新作ゲーム", "web", "q", "dummy",
            searcher=flaky, fetcher=fetcher, sleeper=lambda _: None,
        )
        self.assertTrue(lane["complete"])
        self.assertEqual(lane["searchCalls"], 2)
        self.assertEqual(lane["searchErrors"], 1)
        self.assertEqual(len(lane["sources"]), 1)

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

    def test_auth_or_quota_error_aborts_without_retry(self):
        import urllib.error
        for code in (401, 403, 429, 432, 433):
            calls = {"count": 0}
            def denied(query, key, max_results):
                calls["count"] += 1
                raise urllib.error.HTTPError("https://api.tavily.com/search", code, "x", {}, None)
            with self.assertRaises(r.SearchAborted) as ctx:
                r.research_channel("新作ゲーム", "web", "q", "dummy",
                                   searcher=denied, fetcher=fetcher, sleeper=lambda _: None)
            self.assertEqual(ctx.exception.reason, f"search_http_{code}")
            self.assertEqual(calls["count"], 1)

    def test_other_http_error_keeps_one_bounded_retry(self):
        import urllib.error
        def server_error(query, key, max_results):
            raise urllib.error.HTTPError("https://api.tavily.com/search", 500, "x", {}, None)
        lane = r.research_channel("新作ゲーム", "web", "q", "dummy",
                                  searcher=server_error, fetcher=fetcher, sleeper=lambda _: None)
        self.assertFalse(lane["complete"])
        self.assertEqual(lane["searchCalls"], 2)

    def _run_with(self, search, items=3):
        q = queue()
        base = q["items"][0]
        q["items"] = [dict(base, game=f"新作ゲーム{i}", rank=i + 1) for i in range(items)]
        with tempfile.TemporaryDirectory() as td:
            old_status = r.STATUS
            r.STATUS = Path(td) / "status.json"
            try:
                status = r.run(queue=q, api_key="dummy", searcher=search, fetcher=fetcher,
                               out_dir=Path(td) / "research")
                written = json.loads(r.STATUS.read_text())
                files = list((Path(td) / "research").glob("*.json"))
            finally:
                r.STATUS = old_status
        self.assertEqual(status, written)
        return status, files

    def test_run_stops_on_first_fatal_search_error(self):
        import urllib.error
        calls = {"count": 0}
        def denied(query, key, max_results):
            calls["count"] += 1
            raise urllib.error.HTTPError("https://api.tavily.com/search", 401, "x", {}, None)
        status, files = self._run_with(denied)
        self.assertEqual(calls["count"], 1)
        self.assertEqual(status["apiCalls"], 1)
        self.assertFalse(status["success"])
        self.assertTrue(status["aborted"])
        self.assertEqual(status["abortReason"], "search_http_401")
        self.assertEqual(status["skippedGames"], 2)
        self.assertEqual(status["failures"][0]["reason"], "search_http_401")
        self.assertEqual(status["publicationWrites"], 0)
        self.assertEqual(files, [])
        self.assertNotIn("dummy", json.dumps(status))

    def test_run_stops_after_failed_retry(self):
        calls = {"count": 0}
        def broken(query, key, max_results):
            calls["count"] += 1
            raise TimeoutError("timeout")
        old_sleep = r.time.sleep
        r.time.sleep = lambda _: None
        try:
            status, files = self._run_with(broken)
        finally:
            r.time.sleep = old_sleep
        self.assertEqual(calls["count"], 2)
        self.assertEqual(status["apiCalls"], 2)
        self.assertTrue(status["aborted"])
        self.assertEqual(status["abortReason"], "search_failed_after_retry")
        self.assertFalse(status["success"])
        self.assertEqual(files, [])

    def test_games_before_abort_are_kept(self):
        import urllib.error
        calls = {"count": 0}
        def quota_after_first_game(query, key, max_results):
            calls["count"] += 1
            if calls["count"] > 4:
                raise urllib.error.HTTPError("https://api.tavily.com/search", 432, "x", {}, None)
            return searcher(query, key, max_results)
        status, files = self._run_with(quota_after_first_game)
        self.assertEqual(calls["count"], 5)
        self.assertEqual(status["completeGames"], 1)
        self.assertEqual(len(files), 1)
        self.assertEqual(status["skippedGames"], 1)
        self.assertEqual(status["abortReason"], "search_http_432")
        self.assertFalse(status["success"])

    def test_successful_run_reports_no_abort(self):
        status, files = self._run_with(searcher, items=2)
        self.assertTrue(status["success"])
        self.assertFalse(status["aborted"])
        self.assertIsNone(status["abortReason"])
        self.assertEqual(status["apiCalls"], 8)
        self.assertEqual(len(files), 2)

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
