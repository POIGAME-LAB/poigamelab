import importlib.util
import json
import subprocess
import sys

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


def test_capture_parses_current_reward_and_platform_from_realistic_cards():
    capture = load_capture_module()
    raw = """
    <html><body>
      <a href="/ad/155403/">
        Water Sort Puzzle - ソートパズルゲーム（iOS用）【9/25までの高還元!!】
        3,500pt ⇒ 8,000pt アプリ アプリ保証
      </a>
      <a href="/ad/156173/">
        マフィア・シティ-極道風雲（Android用）
        80,000pt ⇒ 100,000pt アプリ
      </a>
      <a href="/ad/156006/">
        マネーフォワード ME（iOS用） 2,500pt アプリ
      </a>
    </body></html>
    """
    offers = capture.parse_listing_page(
        raw,
        "https://sp.pointi.jp/ajax_load/load_list_site.php?page=1&cat_no=68&od=1",
    )
    assert [x["adId"] for x in offers] == ["155403", "156173", "156006"]
    assert offers[0]["currentPoints"] == 8000
    assert offers[0]["currentYen"] == 800
    assert offers[0]["platform"] == "iOS"
    assert offers[1]["currentPoints"] == 100000
    assert offers[1]["platform"] == "Android"
    assert offers[2]["currentPoints"] == 2500


def test_capture_strips_purchase_amount_before_reward():
    capture = load_capture_module()
    raw = """
    <a href="/ad/146816/">
      100% 還元 カプとれ（Android用） 650円(税込)の商品ご購入で
      3,000pt ⇒ 6,500pt アプリ
    </a>
    """
    offers = capture.parse_listing_page(
        raw,
        "https://sp.pointi.jp/ajax_load/load_list_site.php?page=3&cat_no=68&od=1",
    )
    assert len(offers) == 1
    assert offers[0]["title"] == "100% 還元 カプとれ（Android用）"
    assert offers[0]["currentPoints"] == 6500


def test_importer_accepts_structured_candidate_catalog(tmp_path):
    payload = {
        "schemaVersion": 2,
        "source": "point_income",
        "sourceUrl": "https://sp.pointi.jp/list.php?cat_no=68",
        "pageCount": 4,
        "stoppedBecause": "empty_page",
        "offers": [
            {
                "adId": "156226",
                "url": "https://sp.pointi.jp/ad/156226/",
                "title": "タウンシップ【アプリ利用でptゲット/iOS用】",
                "platform": "iOS",
                "currentPoints": 308302,
            },
            {
                "adId": "149940",
                "title": "エバーテイル（Android用）",
                "platform": "Android",
                "currentPoints": 2500,
            },
        ],
    }
    result, out = run_importer(tmp_path, payload)
    assert result.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["candidateOnly"] is True
    assert data["catalogCompleteClaim"] is False
    assert data["count"] == 2
    assert data["offers"][0]["currentPoints"] == 308302
    assert data["offers"][0]["currentYen"] == 30830.2
    assert data["offers"][0]["publicationAuthorized"] is False


def test_importer_still_accepts_legacy_id_only_payload(tmp_path):
    result, out = run_importer(
        tmp_path,
        {
            "source": "point_income",
            "sourceUrl": "https://pointi.jp/list.php?category=68",
            "adUrls": [
                "https://pointi.jp/ad/149843/",
                "https://sp.pointi.jp/ad/149388/",
                "149843",
                "https://evil.example/ad/999999/",
            ],
        },
    )
    assert result.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [x["adId"] for x in data["offers"]] == ["149843", "149388"]


def test_importer_rejects_empty_or_non_first_party_source(tmp_path):
    result, out = run_importer(
        tmp_path,
        {
            "source": "point_income",
            "sourceUrl": "https://evil.example/list",
            "offers": [],
        },
    )
    assert result.returncode != 0
    assert not out.exists()


def test_capture_detects_first_party_hosts_and_rejects_lookalikes():
    capture = load_capture_module()
    assert capture.first_party("https://pointi.jp/ad/1/") is True
    assert capture.first_party("https://sp.pointi.jp/ad/1/") is True
    assert capture.first_party("https://pointi.jp.evil.example/ad/1/") is False
    assert capture.first_party("http://pointi.jp/ad/1/") is False


def test_capture_dispatch_payload_is_gzip_and_bounded():
    import base64
    import gzip

    capture = load_capture_module()
    payload = {
        "schemaVersion": 2,
        "source": "point_income",
        "offers": [
            {
                "adId": str(150000 + i),
                "url": f"https://sp.pointi.jp/ad/{150000 + i}/",
                "title": f"テストゲーム {i}（iOS用）",
                "platform": "iOS",
                "currentPoints": 1000 + i,
                "currentYen": (1000 + i) / 10,
                "rewardText": f"{1000 + i:,}pt",
            }
            for i in range(300)
        ],
        "count": 300,
    }
    encoded = capture.encode_dispatch_payload(payload)
    assert len(encoded) < capture.MAX_DISPATCH_CHARS
    packed = base64.b64decode(encoded, validate=True)
    raw = gzip.decompress(packed)
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded["count"] == 300
    assert len(decoded["offers"]) == 300


def test_dispatch_request_targets_only_expected_workflow():
    capture = load_capture_module()
    seen = {}

    class Response:
        status = 204
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def fake_open(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["authorization"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    assert capture.dispatch_to_github("abc123", "github_pat_test_token_1234567890", open_url=fake_open)
    assert seen["url"] == (
        "https://api.github.com/repos/POIGAME-LAB/poigamelab/"
        "actions/workflows/import-point-income-device-catalog.yml/dispatches"
    )
    assert seen["authorization"] == "Bearer github_pat_test_token_1234567890"
    assert seen["body"] == {
        "ref": "main",
        "inputs": {"point_income_catalog_base64": "abc123"},
    }
