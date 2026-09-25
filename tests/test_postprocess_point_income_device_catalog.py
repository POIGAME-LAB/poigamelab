import json
import subprocess
import sys


SCRIPT = "scripts/postprocess-point-income-device-catalog.py"


def test_postprocessor_matches_reviewed_aliases_and_keeps_unmatched_apps(tmp_path):
    inp = tmp_path / "catalog.json"
    games = tmp_path / "games.csv"
    matched = tmp_path / "matched.json"
    unmatched = tmp_path / "unmatched.json"

    games.write_text(
        "name,image\n"
        "Township,x\n"
        "ATLAS: EARTH,x\n"
        "エバーテイル,x\n"
        "ファミリーファームの冒険,x\n",
        encoding="utf-8",
    )
    inp.write_text(
        json.dumps({
            "count": 5,
            "offers": [
                {
                    "adId": "1",
                    "url": "https://sp.pointi.jp/ad/1/",
                    "title": "タウンシップ【アプリ利用でptゲット/iOS用】",
                    "platform": "iOS",
                    "currentPoints": 308302,
                    "currentYen": 30830.2,
                },
                {
                    "adId": "2",
                    "url": "https://sp.pointi.jp/ad/2/",
                    "title": "ATLAS:EARTH【アプリステーション/Android用】",
                    "platform": "Android",
                    "currentPoints": 279405,
                    "currentYen": 27940.5,
                },
                {
                    "adId": "3",
                    "url": "https://sp.pointi.jp/ad/3/",
                    "title": "エバーテイル（iOS用）【9/30までの高還元!!】",
                    "platform": "iOS",
                    "currentPoints": 2500,
                    "currentYen": 250,
                },
                {
                    "adId": "4",
                    "url": "https://sp.pointi.jp/ad/4/",
                    "title": "Family Island - ファミリーアイランド（iOS用）",
                    "platform": "iOS",
                    "currentPoints": 18000,
                    "currentYen": 1800,
                },
                {
                    "adId": "5",
                    "url": "https://sp.pointi.jp/ad/5/",
                    "title": "マネーフォワード ME（iOS用）",
                    "platform": "iOS",
                    "currentPoints": 2500,
                    "currentYen": 250,
                },
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, SCRIPT, str(inp), str(games), str(matched), str(unmatched)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    m = json.loads(matched.read_text(encoding="utf-8"))
    assert m["matchedGameCount"] == 3
    assert m["matchedOfferCount"] == 3
    assert [x["game"] for x in m["items"]] == ["Township", "ATLAS: EARTH", "エバーテイル"]
    assert m["items"][0]["bestDisplayedYen"] == 30830.2

    u = json.loads(unmatched.read_text(encoding="utf-8"))
    assert u["count"] == 2
    titles = [x["title"] for x in u["items"]]
    assert "Family Island - ファミリーアイランド（iOS用）" in titles
    assert "マネーフォワード ME（iOS用）" in titles


def test_postprocessor_does_not_confuse_family_island_with_family_farm(tmp_path):
    inp = tmp_path / "catalog.json"
    games = tmp_path / "games.csv"
    matched = tmp_path / "matched.json"
    unmatched = tmp_path / "unmatched.json"

    games.write_text("name,image\nファミリーファームの冒険,x\n", encoding="utf-8")
    inp.write_text(
        json.dumps({
            "offers": [{
                "adId": "9",
                "url": "https://sp.pointi.jp/ad/9/",
                "title": "Family Island - ファミリーアイランド（iOS用）",
                "platform": "iOS",
                "currentPoints": 18000,
                "currentYen": 1800,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, SCRIPT, str(inp), str(games), str(matched), str(unmatched)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    m = json.loads(matched.read_text(encoding="utf-8"))
    assert m["matchedGameCount"] == 0
    u = json.loads(unmatched.read_text(encoding="utf-8"))
    assert u["count"] == 1
