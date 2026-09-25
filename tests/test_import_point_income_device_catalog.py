import importlib.util
import json
import subprocess
import sys
from pathlib import Path

IMPORTER = "scripts/import-point-income-device-catalog.py"
CAPTURE = "scripts/point-income-device-capture.py"


def run_importer(tmp_path, payload):
    inp = tmp_path / "in.json"
    out = tmp_path / "out.json"
    inp.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, IMPORTER, str(inp), str(out)],
        capture_output=True,
        text=True,
    )
    return result, out


def load_capture_module():
    spec = importlib.util.spec_from_file_location("point_income_capture", CAPTURE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importer_accepts_candidate_ids_and_official_urls(tmp_path):
    payload = {
        "source": "point_income",
        "sourceUrl": "https://pointi.jp/list.php?category=game",
        "pageCount": 2,
        "adUrls": [
            "https://pointi.jp/ad/149843/",
            "https://sp.pointi.jp/ad/149388/",
            "149843",
            "https://evil.example/ad/999999/",
        ],
    }
    result, out = run_importer(tmp_path, payload)
    assert result.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source"] == "point_income"
    assert data["candidateOnly"] is True
    assert data["catalogCompleteClaim"] is False
    assert data["pageCount"] == 2
    assert data["adIds"] == ["149843", "149388"]
    assert data["count"] == 2


def test_importer_rejects_empty_or_non_first_party_source(tmp_path):
    result, out = run_importer(
        tmp_path,
        {
            "source": "point_income",
            "sourceUrl": "https://evil.example/list",
            "adUrls": ["https://evil.example/ad/1/"],
        },
    )
    assert result.returncode != 0
    assert not out.exists()

    result, out = run_importer(
        tmp_path,
        {
            "source": "point_income",
            "sourceUrl": "https://pointi.jp/list.php",
            "adUrls": [],
        },
    )
    assert result.returncode != 0
    assert not out.exists()


def test_capture_parser_extracts_only_point_income_ad_ids_and_next_link():
    capture = load_capture_module()
    raw = """
    <html><head>
      <link rel="next" href="/list.php?page=2">
    </head><body>
      <a href="/ad/149843/">Game A</a>
      <a href="https://sp.pointi.jp/ad/149388/">Game B</a>
      <a href="https://evil.example/ad/999999/">Bad</a>
      <a href="/help/detail.php?tno=296">Help</a>
    </body></html>
    """
    ids, next_urls = capture.parse_page(raw, "https://pointi.jp/list.php?page=1")
    assert ids == ["149843", "149388"]
    assert next_urls == ["https://pointi.jp/list.php?page=2"]


def test_capture_detects_first_party_hosts_and_rejects_lookalikes():
    capture = load_capture_module()
    assert capture.first_party("https://pointi.jp/ad/1/") is True
    assert capture.first_party("https://sp.pointi.jp/ad/1/") is True
    assert capture.first_party("https://pointi.jp.evil.example/ad/1/") is False
    assert capture.first_party("http://pointi.jp/ad/1/") is False
