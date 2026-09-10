import importlib.util
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site",
    ROOT / "scripts" / "build_public_site.py",
)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


class LocalReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src", "data-experience-src"} and value:
                self.references.append((tag, key, value))


def local_reference_target(page: Path, reference: str):
    raw = reference.strip()
    if not raw or raw.startswith(("#", "data:", "mailto:", "tel:", "javascript:", "//")):
        return None
    if "$" + "{" in raw or "{{" in raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    if parsed.path.startswith("/"):
        raise AssertionError(f"root-relative reference breaks project Pages: {page.name}: {raw}")
    path = unquote(parsed.path)
    if not path:
        return page
    return (page.parent / path).resolve()


@pytest.fixture
def output_dir():
    path = ROOT / ".test-public-site"
    if path.exists():
        shutil.rmtree(path)
    yield path
    if path.exists():
        shutil.rmtree(path)


def test_public_site_builder_copies_only_launch_allowlist(output_dir):
    copied = builder.build_public_site(output_dir)
    copied_set = set(copied)

    required = {
        "index.html", "game.html", "offers.html", "guides.html", "404.html", "new-game-status.html", "existing-game-status.html",
        "about.html", "privacy.html", "contact.html", "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html", "kingshot-guide.html", "houchishojo-guide.html",
        "evertale-guide.html", "site-data.js", "site-footer.js", "site-referrals.js",
        "site-guides.js", "site-image-rights.js", "site-header.js", "games.js",
        "games.csv", "robots.txt", "sitemap.xml", "CNAME", "poigamelab_icon.png", "assets/guide-experience.css",
        "assets/guide-experience.js", "data/published_offers.csv", "data/offer_history.csv",
        "data/refresh_status.json", "data/exception_queue.json", "data/new_game_monitor.json", "data/existing_game_monitor.json",
        "data/guide-experiences/kinoko.json", "data/guide-experiences/mementomori.json",
        "data/guide-experiences/whiteout-survival.json",
        "data/guide-experiences/working-heroes.json", "config/refresh_policy.json",
    }
    assert required <= copied_set

    forbidden = {
        "offers.csv", "sources.csv", "trend_sources.csv", "README.md", "AGENTS.md",
        "config/approved_offer_baselines.json", "config/offerwall_providers.json",
        "data/warau_baseline_candidates.json", "data/trend_candidates.json",
        "data/research_queue.json",
    }
    assert copied_set.isdisjoint(forbidden)
    for prefix in (".github/", "docs/", "scripts/", "tests/", "data/research_results/"):
        assert not any(path.startswith(prefix) for path in copied_set)
    assert {p for p in copied_set if p.startswith("data/")} == {
        "data/published_offers.csv", "data/offer_history.csv", "data/refresh_status.json",
        "data/exception_queue.json", "data/new_game_monitor.json", "data/existing_game_monitor.json",
        "data/guide-experiences/kinoko.json", "data/guide-experiences/mementomori.json",
        "data/guide-experiences/whiteout-survival.json", "data/guide-experiences/working-heroes.json",
    }
    assert {p for p in copied_set if p.startswith("config/")} == {"config/refresh_policy.json"}


def test_public_artifact_is_self_contained_for_current_managed_games(output_dir):
    builder.build_public_site(output_dir)
    policy = json.loads((output_dir / "config" / "refresh_policy.json").read_text())
    assert set(policy["games"]) == {
        "Township", "きのこ伝説", "メメントモリ", "ワーキングヒーロー",
        "ホワイトアウト・サバイバル", "東京ディバンカー", "パズル＆サバイバル",
        "キングショット", "放置少女", "エバーテイル",
    }
    site_data = (output_dir / "site-data.js").read_text()
    assert "data/published_offers.csv" in site_data
    assert "config/refresh_policy.json" in site_data
    assert not (output_dir / "offers.csv").exists()
    not_found = (output_dir / "404.html").read_text()
    assert 'name="robots" content="noindex,nofollow"' in not_found
    assert 'src="site-footer.js"' in not_found


def test_mementomori_has_verified_published_reward(output_dir):
    builder.build_public_site(output_dir)
    import csv
    rows = list(csv.DictReader((output_dir / "data" / "published_offers.csv").open(encoding="utf-8", newline="")))
    matches = [row for row in rows if row["game"] == "メメントモリ" and row["verified"].lower() == "true"]
    assert matches, "MementoMori must keep at least one verified published offer"
    best = max(matches, key=lambda row: int(row["reward"]))
    assert best["site"] == "warau"
    assert best["platform"] == "iOS"
    assert best["reward"] == "12050"
    assert "point_id=206035" in best["url"]
    assert "ランク140到達" in best["condition"]
    assert "累計10000円課金" in best["condition"]

    review = json.loads((ROOT / "data" / "comparison_review_queue.json").read_text(encoding="utf-8"))
    evidence = next(
        item["sourceEvidence"] for item in review["items"]
        if item["game"] == "メメントモリ"
        and item["source"] == "warau"
        and item.get("sourceEvidence", {}).get("state") == "parsed"
        and item["sourceEvidence"].get("offerId") == "206037"
    )
    published_11500 = next(
        row for row in matches
        if row["url"] == "https://www.warau.jp/contents/point/pointEntrance.php?point_id=206037"
    )
    assert published_11500["platform"] == evidence["platform"]
    assert int(published_11500["reward"]) == evidence["rewardPoints"]

# Remaining tests intentionally unchanged below this point.
