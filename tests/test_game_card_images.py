import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_game_card_images import MAX_BYTES, card_name  # noqa: E402

GAMES = list(csv.DictReader((ROOT / "games.csv").open(encoding="utf-8-sig", newline="")))


def test_card_name_mapping():
    assert card_name("assets/game-art/township-original.jpeg") == "township-original.webp"
    assert card_name("assets/game-art/mementomori-new.png.PNG") == "mementomori-new.webp"
    assert card_name("assets/game-art/whiteout-survival.svg") == ""
    assert card_name("https://example.com/a.png") == ""
    assert card_name("") == ""


def test_every_raster_game_image_has_valid_light_card():
    for row in GAMES:
        image = row["image"].strip()
        name = card_name(image)
        if not name:
            continue
        assert (ROOT / image.split("?", 1)[0]).is_file(), f"missing source: {image}"
        data = (ROOT / "assets/game-cards" / name).read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", f"{name} is not WebP"
        assert len(data) <= MAX_BYTES, f"{name} exceeds {MAX_BYTES} bytes"


def test_manifest_covers_all_games_and_records_source():
    path = ROOT / "docs/game-images/game-image-manifest.csv"
    manifest = {r["name"]: r for r in csv.DictReader(path.open(encoding="utf-8-sig", newline=""))}
    assert set(manifest) == {r["name"] for r in GAMES}
    for row in GAMES:
        entry = manifest[row["name"]]
        assert entry["source_and_license"].strip(), row["name"]
        if row["image"].strip():
            assert "ChatGPT生成画像（運営者確認済み）" in entry["source_and_license"]


def test_pages_use_card_image_helper_with_fallback():
    for page in ("offers.html", "guides.html", "game.html"):
        assert "POIGAME_CARD_IMAGE.attrs(" in (ROOT / page).read_text(encoding="utf-8"), page
    js = (ROOT / "site-image-rights.js").read_text(encoding="utf-8")
    assert "data-full-src" in js and "stopImmediatePropagation" in js
