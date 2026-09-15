import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_new_game_content_packages as b
import new_game_content_gate as gate


def research():
    def lane(channel, sid, url, text):
        return {"searched": True, "complete": True, "sources": [{
            "id": sid, "url": url, "channel": channel, "targetConfirmed": True,
            "poiContext": True, "excerpt": text, "claim": text,
        }]}
    return {
        "phase": "NEW_GAME_MULTI_CHANNEL_RESEARCH_V1",
        "game": "新作ゲーム",
        "complete": True,
        "research": {
            "web": lane(
                "web",
                "web:1",
                "https://example.com/guide",
                "新作ゲームは10日でレベル20到達を目指す攻略例があり、難易度は普通〜やや難。期限とレベル進捗を確認して進める。",
            ),
            "x": lane("x", "x:1", "https://x.com/user/status/123", "新作ゲームのポイ活を7日でレベル18まで進めた公開記録。"),
            "youtube": lane("youtube", "youtube:1", "https://www.youtube.com/watch?v=abc", "新作ゲームのポイ活攻略でレベル20までの進め方を紹介。"),
            "instagram": lane("instagram", "instagram:1", "https://www.instagram.com/p/abc/", "新作ゲームをポイ活で進めている公開投稿。"),
            "pointSites": {"searched": True, "complete": True, "sources": [
                {"id": "pointSites:warau", "url": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=1", "channel": "pointSites", "claim": "warau の同一巡回で案件詳細を確認済み"},
                {"id": "pointSites:amefuri", "url": "https://www.amefri.net/detail/id/2", "channel": "pointSites", "claim": "amefuri の同一巡回で案件詳細を確認済み"},
            ]},
        },
    }


def proposal():
    return {
        "days": "7〜10日",
        "daysSourceRefs": ["x:1", "web:1"],
        "difficulty": "普通〜やや難",
        "difficultySourceRefs": ["web:1"],
        "guide": {
            "title": "新作ゲーム ポイ活攻略まとめ",
            "overview": "公開された攻略情報と案件情報を照合しながら、条件達成を目指すゲームです。",
            "overviewSourceRefs": ["web:1", "pointSites:warau"],
            "tips": "期限とレベル進捗を確認し、公開情報で裏取りできた手順だけを優先します。",
            "tipsSourceRefs": ["web:1"],
            "sections": [
                {"heading": "案件条件", "text": "ポイントサイトで案件詳細が確認されているため、開始前に条件を確認します。", "sourceRefs": ["pointSites:warau", "pointSites:amefuri"]},
                {"heading": "達成ペース", "text": "公開攻略例では10日でレベル20到達を目指す進行例があります。", "sourceRefs": ["web:1"]},
                {"heading": "攻略のポイント", "text": "レベル20までの進め方を扱う公開攻略を参考に、進捗を確認します。", "sourceRefs": ["youtube:1"]},
            ],
        },
        "progress": [{"sourceRef": "x:1", "summary": "公開記録では7日でレベル18まで進んでいます。"}],
    }


class TestBuildNewGameContentPackages(unittest.TestCase):
    def test_valid_synthesis_builds_generated_image_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = b.build_package(research(), proposal(), root=root)
            self.assertTrue(package["publicationReady"])
            self.assertEqual(package["image"]["provenance"], "generated")
            self.assertTrue((root / package["image"]["path"]).is_file())
            self.assertEqual(package["progress"][0]["sourceRef"], "x:1")
            self.assertIn("直接確認できた公開攻略", package["guide"]["intro"])
            result = gate.validate(package, "新作ゲーム", root=root, require_guide_file=False)
            self.assertEqual(result["progressCount"], 1)

    def test_ungrounded_number_is_rejected(self):
        bad = proposal()
        bad["guide"]["sections"][1]["text"] = "公開攻略例では99日でレベル20到達を目指す進行例があります。"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ContentHold, "numeric_ungrounded"):
                b.build_package(research(), bad, root=Path(td))

    def test_progress_requires_social_source(self):
        bad = proposal()
        bad["progress"] = [{"sourceRef": "web:1", "summary": "公開攻略では10日で進行します。"}]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ContentHold, "progress_missing"):
                b.build_package(research(), bad, root=Path(td))

    def test_catalog_summaries_require_source_refs(self):
        bad = proposal()
        bad["guide"].pop("overviewSourceRefs")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ContentHold, "overview_evidence_invalid"):
                b.build_package(research(), bad, root=Path(td))

    def test_catalog_summary_ungrounded_number_is_rejected(self):
        bad = proposal()
        bad["guide"]["overview"] = "99日で条件達成を目指すゲームです。"
        bad["guide"]["overviewSourceRefs"] = ["web:1"]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(gate.ContentHold, "overview_numeric_ungrounded"):
                b.build_package(research(), bad, root=Path(td))

    def test_svg_is_local_original_title_card(self):
        svg = b.neutral_svg("新作ゲーム")
        self.assertIn("POIGAME LAB", svg)
        self.assertIn("新作ゲーム", svg)
        self.assertNotIn("https://", svg)
        self.assertNotIn("<image", svg)


if __name__ == "__main__":
    unittest.main()
