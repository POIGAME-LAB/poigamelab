import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import new_game_content_gate as gate


def package(game="新作ゲーム"):
    return {
        "schemaVersion": 1,
        "game": game,
        "publicationReady": True,
        "research": {
            "web": {"searched": True, "complete": True, "sources": [
                {"id": "web1", "url": "https://example.com/guide", "claim": "レベル到達の攻略情報を確認"}
            ]},
            "x": {"searched": True, "complete": True, "sources": [
                {"id": "x1", "url": "https://x.com/example/status/1", "claim": "10日目の到達記録を確認"}
            ]},
            "youtube": {"searched": True, "complete": True, "sources": []},
            "instagram": {"searched": True, "complete": True, "sources": []},
            "pointSites": {"searched": True, "complete": True, "sources": [
                {"id": "point1", "url": "https://www.warau.jp/example", "claim": "案件条件を確認"}
            ]},
        },
        "guide": {
            "title": "新作ゲーム ポイ活攻略まとめ",
            "intro": "案件達成を目的に、確認できた情報だけを整理した攻略です。",
            "overview": "育成とステージ進行を組み合わせて条件達成を目指すゲームです。",
            "tips": "日課を優先し、必要な育成素材を切らさないように進めます。",
            "sections": [
                {"heading": "序盤", "text": "序盤は日課を開放しながら必要なレベルまで進めます。", "sourceRefs": ["web1", "point1"]},
                {"heading": "中盤", "text": "中盤は資源を温存し、詰まりやすい育成条件を先回りします。", "sourceRefs": ["web1"]},
                {"heading": "進捗", "text": "公開された体験記録は個人差のある参考値として分離して扱います。", "sourceRefs": ["x1"]},
            ],
        },
        "progress": [
            {"identityKey": "x:example", "sourceRef": "x1", "summary": "10日目に目標付近へ到達した公開記録"}
        ],
        "image": {
            "path": "assets/game-art/new-game.png",
            "provenance": "generated",
            "rightsConfirmed": True,
        },
        "guidePath": "new-game-guide.html",
        "days": "10〜14日目安",
        "difficulty": "普通",
    }


def make_files(root, payload=None):
    root = Path(root)
    (root / "assets/game-art").mkdir(parents=True)
    (root / "assets/game-art/new-game.png").write_bytes(b"fake-image-for-path-gate")
    (root / "new-game-guide.html").write_text("<!doctype html><title>guide</title>", encoding="utf-8")
    content = root / "data/new_game_content_packages"
    content.mkdir(parents=True)
    value = payload or package()
    (content / "package.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return content


def test_complete_package_passes():
    with tempfile.TemporaryDirectory() as td:
        content = make_files(td)
        out = gate.validate_for_game("新作ゲーム", content_dir=content, root=td)
        assert out["guidePath"] == "new-game-guide.html"
        assert out["image"] == "assets/game-art/new-game.png"
        assert out["progressCount"] == 1


def test_explicit_unknown_catalog_fields_pass_when_guide_is_grounded():
    with tempfile.TemporaryDirectory() as td:
        p = package()
        p["days"] = "調査中"
        p["difficulty"] = "調査中"
        content = make_files(td, p)
        out = gate.validate_for_game("新作ゲーム", content_dir=content, root=td)
        assert out["days"] == "調査中"
        assert out["difficulty"] == "調査中"
        assert out["catalogPending"] == ["days", "difficulty"]


def test_blank_catalog_fields_still_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        p = package()
        p["days"] = ""
        content = make_files(td, p)
        with pytest.raises(gate.ContentHold, match="catalog_fields_incomplete"):
            gate.validate_for_game("新作ゲーム", content_dir=content, root=td)


def test_missing_research_channel_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        p = package(); del p["research"]["instagram"]
        content = make_files(td, p)
        with pytest.raises(gate.ContentHold, match="research_channel_incomplete:instagram"):
            gate.validate_for_game("新作ゲーム", content_dir=content, root=td)


def test_empty_progress_is_allowed_when_guide_has_grounded_sources():
    with tempfile.TemporaryDirectory() as td:
        p = package()
        p["progress"] = []
        content = make_files(td, p)
        out = gate.validate_for_game("新作ゲーム", content_dir=content, root=td)
        assert out["progressCount"] == 0


def test_point_site_only_guide_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        p = package()
        p["guide"]["sections"] = [{
            "heading": "案件条件",
            "text": "ポイントサイトで確認できた案件条件を開始前に確認してください。",
            "sourceRefs": ["point1"],
        }]
        p["progress"] = []
        content = make_files(td, p)
        with pytest.raises(gate.ContentHold, match="guide_source_diversity_insufficient|guide_non_point_source_missing"):
            gate.validate_for_game("新作ゲーム", content_dir=content, root=td)


def test_duplicate_progress_identity_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        p = package(); p["progress"].append(dict(p["progress"][0]))
        content = make_files(td, p)
        with pytest.raises(gate.ContentHold, match="progress_identity_duplicate_or_missing"):
            gate.validate_for_game("新作ゲーム", content_dir=content, root=td)


def test_image_rights_and_guide_file_are_required():
    with tempfile.TemporaryDirectory() as td:
        p = package(); p["image"]["rightsConfirmed"] = False
        content = make_files(td, p)
        with pytest.raises(gate.ContentHold, match="image_rights_unconfirmed"):
            gate.validate_for_game("新作ゲーム", content_dir=content, root=td)
