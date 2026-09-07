from pathlib import Path


def test_games_csv_uses_stable_tokyo_debunker_wrapper():
    text = Path("games.csv").read_text(encoding="utf-8")
    assert "東京ディバンカー,assets/game-art/tokyo-debunker.svg," in text


def test_tokyo_debunker_wrapper_uses_approved_jpeg():
    svg = Path("assets/game-art/tokyo-debunker.svg").read_text(encoding="utf-8")
    assert 'href="tokyo-debunker.jpeg?v=20260907-1045"' in svg
