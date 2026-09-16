import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import include_generated_guides as include
import register_generated_guides as registry


def package():
    return {
        "schemaVersion": 1, "game": "New Game", "publicationReady": True,
        "research": {
            "web": {"searched": True, "complete": True, "sources": [{"id": "w1", "url": "https://example.com/a", "claim": "攻略根拠"}]},
            "x": {"searched": True, "complete": True, "sources": [{"id": "x1", "url": "https://x.com/a/status/1", "claim": "進捗根拠"}]},
            "youtube": {"searched": True, "complete": True, "sources": []},
            "instagram": {"searched": True, "complete": True, "sources": []},
            "pointSites": {"searched": True, "complete": True, "sources": [{"id": "p1", "url": "https://www.warau.jp/a", "claim": "案件根拠"}]},
        },
        "guide": {
            "title": "New Game ポイ活攻略", "intro": "案件達成向けの確認済み情報を整理します。",
            "overview": "公開情報に基づく攻略と進捗を整理したページです。",
            "tips": "根拠が確認できた攻略だけを掲載して進め方を整理します。",
            "sections": [
                {"heading": "条件", "text": "案件条件はポイントサイトの公開情報を確認して開始します。", "sourceRefs": ["p1"]},
                {"heading": "攻略", "text": "攻略情報は直接確認できた公開ページの内容だけを使います。", "sourceRefs": ["w1"]},
                {"heading": "進捗", "text": "進捗例は個人の公開記録として攻略情報とは分けて扱います。", "sourceRefs": ["x1"]},
            ],
        },
        "progress": [{"identityKey": "x:a", "sourceRef": "x1", "summary": "公開されたプレイヤー進捗の記録です。"}],
        "image": {"path": "assets/game-art/new-game-auto.svg", "provenance": "generated", "rightsConfirmed": True},
        "guidePath": "new-game-guide.html", "days": "10日目安", "difficulty": "普通",
    }


def setup(td):
    root = Path(td)
    (root / "assets/game-art").mkdir(parents=True)
    (root / "data/new_game_content_packages").mkdir(parents=True)
    (root / "assets/game-art/new-game-auto.svg").write_text("<svg>local</svg>", encoding="utf-8")
    (root / "new-game-guide.html").write_text("<!doctype html><title>New Game</title>", encoding="utf-8")
    (root / "games.csv").write_text("name,image\nNew Game,assets/game-art/new-game-auto.svg\n", encoding="utf-8")
    (root / "data/new_game_content_packages/new-game.json").write_text(json.dumps(package()), encoding="utf-8")
    (root / "site-guides.js").write_text("window.POIGAME_GUIDES=Object.freeze({});\n", encoding="utf-8")
    (root / "sitemap.xml").write_text('<?xml version="1.0"?><urlset></urlset>', encoding="utf-8")
    return root


class TestGeneratedGuideRegistry(unittest.TestCase):
    def test_registry_survives_after_private_packages_are_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = setup(td)
            reg = root / "data/generated_guides_registry.json"
            result = registry.run(root=root, content_dir=root / "data/new_game_content_packages",
                                  registry_path=reg, guides_js=root / "site-guides.js", sitemap=root / "sitemap.xml")
            self.assertEqual(result["registered"], 1)
            payload = json.loads(reg.read_text())
            row = payload["guides"]["New Game"]
            self.assertEqual(len(row["guideSha256"]), 64)
            self.assertEqual(len(row["imageSha256"]), 64)
            for p in (root / "data/new_game_content_packages").glob("*"):
                p.unlink()
            (root / "data/new_game_content_packages").rmdir()
            artifact = root / "_site"; artifact.mkdir()
            (artifact / "site-guides.js").write_text((root / "site-guides.js").read_text(), encoding="utf-8")
            (artifact / "sitemap.xml").write_text((root / "sitemap.xml").read_text(), encoding="utf-8")
            guides = include.include(artifact, root=root, content_dir=root / "missing", registry_path=reg)
            self.assertEqual(guides, ["new-game-guide.html"])
            self.assertTrue((artifact / "new-game-guide.html").is_file())

    def test_tampered_guide_is_blocked_by_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = setup(td)
            reg = root / "data/generated_guides_registry.json"
            registry.run(root=root, content_dir=root / "data/new_game_content_packages",
                         registry_path=reg, guides_js=root / "site-guides.js", sitemap=root / "sitemap.xml")
            (root / "new-game-guide.html").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "guide_hash_mismatch"):
                include.registry_rows(root=root, registry_path=reg)

    def test_previous_registry_entries_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = setup(td)
            reg = root / "data/generated_guides_registry.json"
            reg.write_text(json.dumps({"schemaVersion": 1, "guides": {"Old Game": {
                "title": "Old", "description": "Old", "guidePath": "old-game-guide.html",
                "guideSha256": "a" * 64, "imagePath": "assets/game-art/old.svg", "imageSha256": "b" * 64
            }}}), encoding="utf-8")
            out, added = registry.merge_registry(root=root, content_dir=root / "data/new_game_content_packages", registry_path=reg)
            self.assertIn("Old Game", out["guides"])
            self.assertIn("New Game", out["guides"])
            self.assertEqual(added, ["New Game"])


if __name__ == "__main__":
    unittest.main()
