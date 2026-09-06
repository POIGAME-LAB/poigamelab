import hashlib
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site_game_art_quality",
    ROOT / "scripts" / "build_public_site.py",
)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)

EXPECTED = {
    "township.webp": {
        "size": 356920,
        "sha256": "394f7007846848626167ad450c7ef00b50394a0bf8582f32bec00ae90e455068",
    },
    "kinoko.webp": {
        "size": 364828,
        "sha256": "89e207811bde0f3e14692cc24854799f2222b82b9b9ba53f18e9cbdfa72cbd5b",
    },
    "whiteout-survival.webp": {
        "size": 511874,
        "sha256": "6777c8f3403d31eda027499562caeff4bb0953804e8b5c7f1090497600b4f710",
    },
}


def test_published_game_art_matches_locally_decoded_high_quality_sources():
    output = ROOT / ".test-game-art-quality"
    if output.exists():
        shutil.rmtree(output)
    try:
        builder.build_public_site(output)
        for filename, expected in EXPECTED.items():
            path = output / "assets" / "game-art" / filename
            data = path.read_bytes()
            assert len(data) == expected["size"], filename
            assert hashlib.sha256(data).hexdigest() == expected["sha256"], filename
            assert data[:4] == b"RIFF", filename
            assert data[8:12] == b"WEBP", filename

        # Private transport chunks must never be published with the site.
        assert not (output / ".asset-source").exists()
    finally:
        if output.exists():
            shutil.rmtree(output)
