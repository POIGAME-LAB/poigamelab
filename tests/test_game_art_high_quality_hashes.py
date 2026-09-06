from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "assets/game-art/township.webp": {
        "size": 412704,
        "sha256": "426124877a8becb895fb0afe6808b5c3627aa225766d6a7e31c78029fd79effc",
    },
    "assets/game-art/kinoko.webp": {
        "size": 425810,
        "sha256": "76f7172c4b8ef4cfb16e645e7f651d1212ea2e7827bedf11f0c275d5737d8c08",
    },
    "assets/game-art/whiteout-survival.webp": {
        "size": 599716,
        "sha256": "d295674208498284f22bd53ca0e056ebcbcfbc22c4a1ed155ac736875f22ba7d",
    },
}


def test_user_approved_game_art_matches_full_resolution_high_quality_exports():
    for relative_path, expected in EXPECTED.items():
        path = ROOT / relative_path
        data = path.read_bytes()
        assert len(data) == expected["size"], relative_path
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], relative_path
        assert data[:4] == b"RIFF", relative_path
        assert data[8:12] == b"WEBP", relative_path
