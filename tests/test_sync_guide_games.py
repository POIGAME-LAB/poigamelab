"""Guide games are registered in the catalog and the daily refresh (operator decision 2026-11-24)."""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_guide_games as sync  # noqa: E402

FILES = ["games.csv", "config/guide_catalog.json", "config/refresh_policy.json",
         "config/game_targets.json", "config/point_sources.json", "site-researched-guides.js"]


def copy_tree(tmp: Path) -> Path:
    for rel in FILES:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp / rel)
    for entry in json.loads((ROOT / "config/guide_catalog.json").read_text(encoding="utf-8"))["games"]:
        shutil.copy(ROOT / entry["guide"], tmp / entry["guide"])
    for href in sync.researched_guide_games(ROOT).values():
        if (ROOT / href).is_file():
            shutil.copy(ROOT / href, tmp / href)
    return tmp


def strip_catalog_games(tmp: Path) -> None:
    """Undo the registration so apply() has to do it again."""
    names = {e["game"] for e in json.loads((tmp / "config/guide_catalog.json").read_text(encoding="utf-8"))["games"]}
    text = (tmp / "games.csv").read_text(encoding="utf-8").splitlines(keepends=True)
    (tmp / "games.csv").write_text("".join([text[0]] + [l for l in text[1:] if l.split(",", 1)[0] not in names]),
                                   encoding="utf-8")
    policy = json.loads((tmp / "config/refresh_policy.json").read_text(encoding="utf-8"))
    policy["games"] = {k: v for k, v in policy["games"].items() if k not in names}
    (tmp / "config/refresh_policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    targets = json.loads((tmp / "config/game_targets.json").read_text(encoding="utf-8"))
    targets["games"] = [t for t in targets["games"] if t["game"] not in names]
    (tmp / "config/game_targets.json").write_text(json.dumps(targets, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")


def test_repository_is_in_sync():
    assert sync.problems(ROOT) == []


def test_check_command_passes():
    result = subprocess.run([sys.executable, "scripts/sync_guide_games.py", "--check"], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "guide games: ok" in result.stdout


def test_every_researched_guide_game_is_listed():
    catalog = {r["name"] for r in csv.DictReader((ROOT / "games.csv").open(encoding="utf-8"))}
    missing = [g for g in sync.researched_guide_games(ROOT) if g not in catalog]
    assert missing == []


def test_new_rows_have_no_image_and_are_not_featured():
    names = {e["game"] for e in sync.load(ROOT)}
    rows = [r for r in csv.DictReader((ROOT / "games.csv").open(encoding="utf-8")) if r["name"] in names]
    assert len(rows) == len(names)
    assert all(r["image"] == "" and r["featured"] == "false" and r["provisionalReward"] == "" for r in rows)


def test_apply_is_idempotent_and_keeps_existing_rows(tmp_path):
    tmp = copy_tree(tmp_path)
    strip_catalog_games(tmp)
    before = (tmp / "games.csv").read_text(encoding="utf-8")
    assert sync.problems(tmp)  # unregistered games are reported
    changed = sync.apply(tmp)
    assert any(c.startswith("games.csv +") for c in changed)
    after = (tmp / "games.csv").read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n"))  # existing rows untouched
    assert sync.problems(tmp) == []
    assert sync.apply(tmp) == []  # second run changes nothing
    policy = json.loads((tmp / "config/refresh_policy.json").read_text(encoding="utf-8"))["games"]
    assert policy["ウォーターパークボーイズ（WaterPark Boys）"]["enabled"] is True


def test_guide_without_catalog_entry_fails_check(tmp_path):
    tmp = copy_tree(tmp_path)
    strip_catalog_games(tmp)
    cfg = json.loads((tmp / "config/guide_catalog.json").read_text(encoding="utf-8"))
    cfg["games"] = [e for e in cfg["games"] if e["game"] != "トップウォー"]
    (tmp / "config/guide_catalog.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    assert any("guide without catalog entry: トップウォー" in p for p in sync.problems(tmp))


def test_offer_urls_come_from_the_guide_page():
    sources = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
    urls = sync.guide_offer_urls(ROOT, "waterpark-boys-guide.html", sources)
    assert set(urls) <= {s for s in sources}
    assert urls, "WaterPark Boys guide links registered first-party offers"
