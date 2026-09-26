import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh-point-income-listing-only.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pi_listing_refresh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path, rows):
    fields = [
        "offerKey", "game", "site", "provider", "reward", "condition", "platform",
        "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def aliases_file(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(
        '{"version":1,"games":[{"game":"エバーテイル","aliases":["エバーテイル","Evertale"]}]}',
        encoding="utf-8",
    )
    return path


def base_row():
    return {
        "offerKey": "エバーテイル|point_income|Android|https://sp.pointi.jp/ad/149940/",
        "game": "エバーテイル",
        "site": "point_income",
        "provider": "",
        "reward": "250",
        "condition": "条件",
        "platform": "Android",
        "type": "通常",
        "deadline": "10日以内",
        "updatedAt": "2026-09-25",
        "url": "https://sp.pointi.jp/ad/149940/",
        "sourceUrl": "https://sp.pointi.jp/ad/149940/",
        "verified": "true",
    }


def catalog(points=3000, title="エバーテイル（Android用）"):
    return {
        "source": "point_income",
        "pointRate": "10pt=1JPY",
        "offers": [{
            "adId": "149940",
            "url": "https://sp.pointi.jp/ad/149940/",
            "title": title,
            "platform": "Android",
            "currentPoints": points,
        }],
    }


def test_exact_verified_identity_updates_reward_only(tmp_path):
    m = load_module()
    out = tmp_path / "published.csv"
    row = base_row()
    write_csv(out, [row])
    changed = m.refresh(catalog(), out, aliases_file(tmp_path), updated_at="2026-09-26")
    assert len(changed) == 1
    with out.open(encoding="utf-8", newline="") as f:
        saved = list(csv.DictReader(f))[0]
    assert saved["reward"] == "300"
    assert saved["condition"] == "条件"
    assert saved["deadline"] == "10日以内"
    assert saved["updatedAt"] == "2026-09-26"


def test_new_offer_is_never_added(tmp_path):
    m = load_module()
    out = tmp_path / "published.csv"
    write_csv(out, [base_row()])
    value = catalog()
    value["offers"][0] = {
        "adId": "999999",
        "url": "https://sp.pointi.jp/ad/999999/",
        "title": "エバーテイル（Android用）",
        "platform": "Android",
        "currentPoints": 4000,
    }
    changed = m.refresh(value, out, aliases_file(tmp_path), updated_at="2026-09-26")
    assert changed == []
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["reward"] == "250"


def test_platform_or_alias_mismatch_fails_closed(tmp_path):
    m = load_module()
    out = tmp_path / "published.csv"
    write_csv(out, [base_row()])
    bad = catalog(title="別ゲーム（Android用）")
    changed = m.refresh(bad, out, aliases_file(tmp_path), updated_at="2026-09-26")
    assert changed == []
    bad = catalog()
    bad["offers"][0]["platform"] = "iOS"
    changed = m.refresh(bad, out, aliases_file(tmp_path), updated_at="2026-09-26")
    assert changed == []


def test_fractional_yen_keeps_last_known_good(tmp_path):
    m = load_module()
    out = tmp_path / "published.csv"
    write_csv(out, [base_row()])
    changed = m.refresh(catalog(points=2505), out, aliases_file(tmp_path), updated_at="2026-09-26")
    assert changed == []
    with out.open(encoding="utf-8", newline="") as f:
        saved = list(csv.DictReader(f))[0]
    assert saved["reward"] == "250"
