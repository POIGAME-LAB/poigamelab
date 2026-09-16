import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_daily_publication import validate


def write_rows(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


@pytest.mark.parametrize("defect", [None, "duplicate", "deleted", "identity", "amount", "url", "stale", "private"])
def test_actual_artifact_gate(tmp_path, defect):
    (tmp_path / "data").mkdir(); (tmp_path / "config").mkdir()
    artifact = tmp_path / "_site"; artifact.mkdir()
    (artifact / "data").mkdir(); (artifact / "config").mkdir()
    (tmp_path / "games.csv").write_text("name\nGame\n")
    (tmp_path / "config/point_sources.json").write_text(json.dumps({"sources": [
        {"id": "warau", "search_domains": ["www.warau.jp"]}]}))
    (tmp_path / "config/refresh_policy.json").write_text("{}")
    row = {"offerKey": "one", "game": "Game", "site": "warau", "platform": "iOS",
           "reward": "100", "condition": "Confirmed", "verified": "true",
           "url": "https://www.warau.jp/detail?id=1", "sourceUrl": "https://www.warau.jp/detail?id=1"}
    baseline = tmp_path / "before.csv"; write_rows(baseline, [row])
    rows = [dict(row)]
    if defect == "duplicate": rows.append(dict(row))
    if defect == "deleted": rows[0]["offerKey"] = "another"
    if defect == "identity": rows[0]["platform"] = "Android"
    if defect == "amount": rows[0]["reward"] = "0"
    if defect == "url": rows[0]["sourceUrl"] = "https://unknown.example"
    write_rows(tmp_path / "data/published_offers.csv", rows)
    for name in ("games.csv", "data/published_offers.csv", "config/refresh_policy.json"):
        (artifact / name).write_bytes((tmp_path / name).read_bytes())
    for name in ("index.html", "offers.html", "game.html", "guides.html", "site-data.js"):
        (artifact / name).write_text("fixture")
    if defect == "stale": (artifact / "data/published_offers.csv").write_text("old")
    if defect == "private": (artifact / "data/daily_scan_review.json").write_text("{}")
    if defect:
        with pytest.raises(ValueError): validate(tmp_path, baseline, artifact)
    else:
        assert validate(tmp_path, baseline, artifact)["preservedOfferIdentities"] == 1
