from pathlib import Path


def test_games_csv_uses_approved_tokyo_debunker_jpeg_directly():
    text = Path("games.csv").read_text(encoding="utf-8")
    assert "東京ディバンカー,assets/game-art/tokyo-debunker.jpeg," in text


def test_tokyo_debunker_jpeg_is_cache_busted_at_render_time():
    js = Path("site-image-rights.js").read_text(encoding="utf-8")
    assert '["assets/game-art/tokyo-debunker.jpeg", "20260907-1208"]' in js
