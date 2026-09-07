from hashlib import sha256
from pathlib import Path


ART_PATH = Path("assets/game-art/tokyo-debunker.jpeg")
EXPECTED_SIZE = 512_191
EXPECTED_SHA256 = "3d138e0b2bcdc93d72ec1437b17ca45ca5fa5bdda22259452a89ea754a90a214"


def test_tokyo_debunker_art_integrity():
    data = ART_PATH.read_bytes()
    assert len(data) == EXPECTED_SIZE
    assert sha256(data).hexdigest() == EXPECTED_SHA256
    assert data.startswith(b"\xff\xd8\xff")
