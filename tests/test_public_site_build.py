import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site",
    ROOT / "scripts" / "build_public_site.py",
)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


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
        "index.html",
        "game.html",
        "404.html",
        "about.html",
        "privacy.html",
        "contact.html",
        "site-data.js",
        "site-footer.js",
        "games.js",
        "games.csv",
        "robots.txt",
        "poigamelab_icon.png",
        "assets/guide-experience.css",
        "assets/guide-experience.js",
        "data/published_offers.csv",
        "data/refresh_status.json",
        "data/exception_queue.json",
        "config/refresh_policy.json",
    }
    assert required <= copied_set

    forbidden = {
        "offers.csv",
        "sources.csv",
        "trend_sources.csv",
        "README.md",
        "AGENTS.md",
        "config/approved_offer_baselines.json",
        "config/offerwall_providers.json",
        "data/warau_baseline_candidates.json",
        "data/trend_candidates.json",
        "data/research_queue.json",
    }
    assert copied_set.isdisjoint(forbidden)

    for prefix in (".github/", "docs/", "scripts/", "tests/", "data/research_results/"):
        assert not any(path.startswith(prefix) for path in copied_set)

    # The build should contain only explicitly published data/config subfiles.
    assert {p for p in copied_set if p.startswith("data/")} == {
        "data/published_offers.csv",
        "data/refresh_status.json",
        "data/exception_queue.json",
    }
    assert {p for p in copied_set if p.startswith("config/")} == {
        "config/refresh_policy.json",
    }


def test_public_artifact_is_self_contained_for_current_managed_games(output_dir):
    builder.build_public_site(output_dir)

    policy = json.loads((output_dir / "config" / "refresh_policy.json").read_text())
    assert set(policy["games"]) == {
        "Township",
        "きのこ伝説",
        "メメントモリ",
        "ワーキングヒーロー",
        "ホワイトアウト・サバイバル",
    }

    site_data = (output_dir / "site-data.js").read_text()
    assert "data/published_offers.csv" in site_data
    assert "config/refresh_policy.json" in site_data

    # Legacy placeholder offers are deliberately not deployed.
    assert not (output_dir / "offers.csv").exists()

    not_found = (output_dir / "404.html").read_text()
    assert 'name="robots" content="noindex,nofollow"' in not_found
    assert 'src="site-footer.js"' in not_found


def test_builder_rejects_unsafe_output_locations(tmp_path):
    with pytest.raises(ValueError, match="unsafe_output_directory"):
        builder.build_public_site(ROOT)
    with pytest.raises(ValueError, match="unsafe_output_directory"):
        builder.build_public_site(tmp_path / "outside")
