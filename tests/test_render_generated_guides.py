import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_new_game_guide as renderer
import include_generated_guides as include


def package():
    return {
        "schemaVersion": 1, "game": "New Game", "publicationReady": True,
        "research": {
            "web": {"searched": True, "complete": True, "sources": [{"id": "w1", "url": "https://example.com/a", "claim": "攻略手順の根拠"}]},
            "x": {"searched": True, "complete": True, "sources": [{"id": "x1", "url": "https://x.com/a/status/1", "claim": "到達日数の公開記録"}]},
            "youtube": {"searched": True, "complete": True, "sources": []},
            "instagram": {"searched": True, "complete": True, "sources": []},
            "pointSites": {"searched": True, "complete": True, "sources": [{"id": "p1", "url": "https://www.warau.jp/a", "claim": "案件条件の根拠"}]},
        },
        "guide": {
            "title": "New Game ポイ活攻略まとめ", "intro": "案件達成に必要な確認済み情報を整理した攻略ページです。",
            "overview": "育成とステージ進行を組み合わせて案件条件の達成を狙うゲームです。",
            "tips": "毎日の日課と資源管理を優先し、詰まりやすい条件を先回りします。",
            "sections": [
                {"heading": "序盤", "text": "序盤は日課を開放しながら必要な育成条件まで進めます。", "sourceRefs": ["w1", "p1"]},
                {"heading": "中盤", "text": "中盤は資源を温存し、次の育成条件を見ながら進めます。", "sourceRefs": ["w1"]},
                {"heading": "進捗", "text": "公開された進捗は個人差のある体験例として分離して扱います。", "sourceRefs": ["x1"]},
            ],
        },
        "progress": [{"identityKey": "x:a", "sourceRef": "x1", "summary": "10日目前後に到達した公開記録"}],
        "image": {"path": "assets/game-art/new-game.png", "provenance": "generated", "rightsConfirmed": True},
        "guidePath": "new-game-guide.html", "days": "10〜14日目安", "difficulty": "普通",
    }


def setup_root(td, adopted=True):
    root = Path(td); (root / "assets/game-art").mkdir(parents=True); (root / "data/new_game_content_packages").mkdir(parents=True)
    (root / "assets/game-art/new-game.png").write_bytes(b"image")
    names = "Township\n" + ("New Game\n" if adopted else "")
    (root / "games.csv").write_text("name\n" + names, encoding="utf-8")
    (root / "data/new_game_content_packages/p.json").write_text(json.dumps(package()), encoding="utf-8")
    artifact = root / "_site"; artifact.mkdir();
    (artifact / "site-guides.js").write_text("window.POIGAME_GUIDES=Object.freeze({});\n", encoding="utf-8")
    (artifact / "sitemap.xml").write_text('<?xml version="1.0"?><urlset></urlset>', encoding="utf-8")
    return root, artifact


def test_renderer_then_artifact_inclusion_makes_reachable_guide():
    with tempfile.TemporaryDirectory() as td:
        root, artifact = setup_root(td, adopted=True)
        rendered = renderer.render_game("New Game", root / "data/new_game_content_packages", root)
        assert rendered["guidePath"] == "new-game-guide.html"
        html = (root / "new-game-guide.html").read_text(encoding="utf-8")
        assert "みんなの進捗" in html and "New Game ポイ活攻略" in html
        guides = include.include(artifact, root=root, content_dir=root / "data/new_game_content_packages")
        assert guides == ["new-game-guide.html"]
        assert (artifact / "new-game-guide.html").is_file()
        registry = (artifact / "site-guides.js").read_text(encoding="utf-8")
        assert "POIGAME_GENERATED_GUIDES_V1" in registry and "new-game-guide.html" in registry
        sitemap = (artifact / "sitemap.xml").read_text(encoding="utf-8")
        assert "https://poigamelab.com/new-game-guide.html" in sitemap
        assert not (artifact / "data/new_game_content_packages").exists()


def test_renderer_omits_empty_player_progress_section():
    with tempfile.TemporaryDirectory() as td:
        root, _ = setup_root(td, adopted=True)
        path = root / "data/new_game_content_packages/p.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["progress"] = []
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        renderer.render_game("New Game", root / "data/new_game_content_packages", root)
        html = (root / "new-game-guide.html").read_text(encoding="utf-8")
        assert "みんなの進捗" not in html
        assert "調査した出典" in html


def test_unadopted_package_is_not_exposed():
    with tempfile.TemporaryDirectory() as td:
        root, artifact = setup_root(td, adopted=False)
        renderer.render_game("New Game", root / "data/new_game_content_packages", root)
        assert include.include(artifact, root=root, content_dir=root / "data/new_game_content_packages") == []
        assert not (artifact / "new-game-guide.html").exists()
        assert "new-game-guide.html" not in (artifact / "sitemap.xml").read_text(encoding="utf-8")
