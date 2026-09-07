from pathlib import Path


def test_games_csv_uses_approved_tokyo_debunker_image():
    text = Path("games.csv").read_text(encoding="utf-8")
    assert "東京ディバンカー,assets/game-art/tokyo-debunker.jpeg," in text
