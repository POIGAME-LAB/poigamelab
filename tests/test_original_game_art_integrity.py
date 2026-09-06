from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "assets/game-art/township-original.jpeg": {
        "size": 530582,
        "sha256": "7dcb52f8cd54d867b700233fe9cc891485bb7175fae4b2fe490e87f5ea84a75a",
        "dimensions": (1536, 864),
    },
    "assets/game-art/kinoko-original.jpeg": {
        "size": 533773,
        "sha256": "5ec27292185370b8892a6968ff619716f3feacbbdbe396452aec68595690878d",
        "dimensions": (1536, 864),
    },
    "assets/game-art/whiteout-survival-original.jpeg": {
        "size": 665140,
        "sha256": "e25e8bb3eedf075b7f3bbb96d1150fcfb6960e3d6cbcaccf728bfee4cd39b159",
        "dimensions": (1448, 1086),
    },
}


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if data[:2] != b"\xff\xd8":
        raise AssertionError("missing JPEG SOI marker")

    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset:offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            break
        if marker in {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }:
            if segment_length < 7:
                break
            height = int.from_bytes(data[offset + 3:offset + 5], "big")
            width = int.from_bytes(data[offset + 5:offset + 7], "big")
            return width, height
        offset += segment_length

    raise AssertionError("JPEG dimensions not found")


def test_user_approved_original_game_art_is_byte_exact_and_full_resolution():
    for relative_path, expected in EXPECTED.items():
        path = ROOT / relative_path
        data = path.read_bytes()
        assert len(data) == expected["size"], relative_path
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], relative_path
        assert data[:2] == b"\xff\xd8", relative_path
        assert data[-2:] == b"\xff\xd9", relative_path
        assert _jpeg_dimensions(data) == expected["dimensions"], relative_path
