from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "import-point-income-device-catalog.yml"


def text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_device_import_accepts_gzip_base64_and_keeps_size_guards():
    value = text()
    assert "gzip.decompress" in value
    assert 'packed[:2] == bytes.fromhex("1f8b")' in value
    assert "compressed payload too large" in value
    assert "payload too large" in value


def test_device_import_persists_only_validated_outputs_to_r2():
    value = text()
    validate = value.index("- name: Validate fail-closed catalog")
    postprocess = value.index("- name: Build existing-game and unmatched-app review queues")
    archive = value.index("- name: Persist accepted device catalog to Cloudflare R2")
    assert validate < postprocess < archive
    block = value[archive:]
    for secret in (
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT",
        "R2_BUCKET",
    ):
        assert f"secrets.{secret}" in block
    assert "device/point-income/daily/" in block
    assert "device/point-income/latest/" in block
    assert "point-income-device-accepted.json" in block
    assert "point-income-existing-game-candidates.json" in block
    assert "point-income-unmatched-app-candidates.json" in block
