from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WEBP_FILES = [
    ROOT / "assets/game-art/township.webp",
    ROOT / "assets/game-art/kinoko.webp",
    ROOT / "assets/game-art/whiteout-survival.webp",
]

PNG_FILES = [
    ROOT / "assets/game-art/puzzles-survival.png",
    ROOT / "assets/game-art/houchishojo.png",
]


def test_selected_game_art_has_valid_webp_container_header():
    for path in WEBP_FILES:
        data = path.read_bytes()
        assert len(data) >= 12, f"{path} is too short"
        assert data[:4] == b"RIFF", f"{path} missing RIFF header"
        assert data[8:12] == b"WEBP", f"{path} missing WEBP signature"
        assert len(data) > 1000, f"{path} is unexpectedly small"


def test_repaired_game_card_art_has_valid_png_header():
    for path in PNG_FILES:
        data = path.read_bytes()
        assert len(data) >= 8, f"{path} is too short"
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} missing PNG signature"
        assert len(data) > 1000, f"{path} is unexpectedly small"
