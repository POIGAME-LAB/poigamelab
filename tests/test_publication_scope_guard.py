import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_scope_guard as guard
import validate_daily_publication as daily_validation

FIELDS = [
    "offerKey", "game", "site", "provider", "reward", "condition", "platform",
    "type", "deadline", "updatedAt", "url", "sourceUrl", "verified"
]


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sample_row(key, site, verified="true"):
    domains = {
        "moppy": "https://pc.moppy.jp/ad/detail.php?site_id=1",
        "chobirich": "https://www.chobirich.com/ad_details/1",
    }
    url = domains[site]
    return {
        "offerKey": key,
        "game": "Game",
        "site": site,
        "provider": "",
        "reward": "600",
        "condition": "新規アプリインストール後に条件達成",
        "platform": "Android",
        "type": "通常",
        "deadline": "30日以内",
        "updatedAt": "2026-09-08",
        "url": url,
        "sourceUrl": url,
        "verified": verified,
    }


def test_repository_current_price_sources_are_bounded_by_unified_eight():
    policy = json.loads((ROOT / "config" / "refresh_policy.json").read_text(encoding="utf-8"))
    unified = policy["unifiedDailySources"]
    current = policy["publication"]["currentPriceSources"]

    assert len(unified) == 8
    assert len(current) == 7
    assert len(set(current)) == len(current)
    assert set(current) <= set(unified)
    assert set(current) == {
        "moppy", "warau", "coincome", "hapitas", "amefuri", "point_town", "ec_navi"
    }
    assert "powl" not in current
    assert "chobirich" not in current


def test_guard_deactivates_only_out_of_scope_rows_and_preserves_history(tmp_path):
    policy = tmp_path / "policy.json"
    published = tmp_path / "published.csv"
    policy.write_text(json.dumps({
        "unifiedDailySources": ["moppy", "warau", "powl"],
        "publication": {"currentPriceSources": ["moppy", "warau"]},
    }), encoding="utf-8")
    active = sample_row("moppy-1", "moppy")
    archived = sample_row("chobi-1", "chobirich")
    archived_before = dict(archived)
    write_rows(published, [active, archived])

    result = guard.enforce_scope(published, policy)
    with published.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert result["deactivatedRows"] == 1
    assert result["networkCalls"] == 0
    assert result["reactivatedRows"] == 0
    assert result["deletedRows"] == 0
    assert len(rows) == 2
    assert rows[0] == active
    assert rows[1]["verified"] == "false"
    for field in FIELDS:
        if field != "verified":
            assert rows[1][field] == archived_before[field]

    second = guard.enforce_scope(published, policy)
    assert second["deactivatedRows"] == 0


def test_guard_never_reactivates_previously_archived_rows(tmp_path):
    policy = tmp_path / "policy.json"
    published = tmp_path / "published.csv"
    policy.write_text(json.dumps({
        "unifiedDailySources": ["moppy"],
        "publication": {"currentPriceSources": ["moppy"]},
    }), encoding="utf-8")
    row = sample_row("moppy-old", "moppy", verified="false")
    write_rows(published, [row])

    result = guard.enforce_scope(published, policy)
    with published.open(encoding="utf-8", newline="") as handle:
        after = list(csv.DictReader(handle))[0]
    assert result["reactivatedRows"] == 0
    assert after["verified"] == "false"


@pytest.mark.parametrize("payload", [
    {"unifiedDailySources": ["moppy"], "publication": {}},
    {"unifiedDailySources": ["moppy"], "publication": {"currentPriceSources": []}},
    {"unifiedDailySources": ["moppy"], "publication": {"currentPriceSources": ["chobirich"]}},
    {"unifiedDailySources": ["moppy"], "publication": {"currentPriceSources": ["moppy", "moppy"]}},
])
def test_invalid_scope_policy_is_fail_closed(tmp_path, payload):
    policy = tmp_path / "policy.json"
    published = tmp_path / "published.csv"
    policy.write_text(json.dumps(payload), encoding="utf-8")
    write_rows(published, [sample_row("moppy-1", "moppy")])
    before = published.read_bytes()
    with pytest.raises(ValueError):
        guard.enforce_scope(published, policy)
    assert published.read_bytes() == before


def test_daily_validator_allows_preserved_archived_row_but_not_invalid_flag(tmp_path):
    root = tmp_path / "root"
    artifact = tmp_path / "artifact"
    baseline = tmp_path / "baseline.csv"
    (root / "data").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (artifact / "data").mkdir(parents=True)
    (artifact / "config").mkdir(parents=True)

    (root / "games.csv").write_text("name\nGame\n", encoding="utf-8")
    source_payload = {"sources": [
        {"id": "moppy", "search_domains": ["pc.moppy.jp"]},
        {"id": "chobirich", "search_domains": ["www.chobirich.com"]},
    ]}
    (root / "config" / "point_sources.json").write_text(json.dumps(source_payload), encoding="utf-8")
    (root / "config" / "refresh_policy.json").write_text("{}\n", encoding="utf-8")

    old_rows = [sample_row("moppy-1", "moppy"), sample_row("chobi-1", "chobirich")]
    current_rows = [sample_row("moppy-1", "moppy"), sample_row("chobi-1", "chobirich", verified="false")]
    write_rows(baseline, old_rows)
    write_rows(root / "data" / "published_offers.csv", current_rows)

    for relative in ["games.csv", "data/published_offers.csv", "config/refresh_policy.json"]:
        target = artifact / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    for name in ["index.html", "offers.html", "game.html", "guides.html", "site-data.js"]:
        (artifact / name).write_text("", encoding="utf-8")

    result = daily_validation.validate(root, baseline, artifact)
    assert result["valid"] is True
    assert result["publishedRows"] == 2

    broken = current_rows
    broken[1] = {**broken[1], "verified": "maybe"}
    write_rows(root / "data" / "published_offers.csv", broken)
    (artifact / "data" / "published_offers.csv").write_bytes(
        (root / "data" / "published_offers.csv").read_bytes()
    )
    with pytest.raises(ValueError, match="invalid_verified_flag"):
        daily_validation.validate(root, baseline, artifact)
