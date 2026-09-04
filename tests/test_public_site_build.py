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
        "index.html",
        "game.html",
        "404.html",
        "about.html",
        "privacy.html",
        "contact.html",
        "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html",
        "kingshot-guide.html",
        "site-data.js",
        "site-footer.js",
        "site-referrals.js",
        "site-guides.js",
        "games.js",
        "games.csv",
        "robots.txt",
        "poigamelab_icon.png",
        "assets/guide-experience.css",
        "assets/guide-experience.js",
        "data/published_offers.csv",
        "data/offer_history.csv",
        "data/refresh_status.json",
        "data/exception_queue.json",
        "data/guide-experiences/kinoko.json",
        "data/guide-experiences/mementomori.json",
        "data/guide-experiences/whiteout-survival.json",
        "data/guide-experiences/working-heroes.json",
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
        "data/offer_history.csv",
        "data/refresh_status.json",
        "data/exception_queue.json",
        "data/guide-experiences/kinoko.json",
        "data/guide-experiences/mementomori.json",
        "data/guide-experiences/whiteout-survival.json",
        "data/guide-experiences/working-heroes.json",
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
        "東京ディバンカー",
        "パズル＆サバイバル",
        "キングショット",
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


def test_all_static_local_html_references_exist_in_public_artifact(output_dir):
    builder.build_public_site(output_dir)
    output_root = output_dir.resolve()
    failures = []

    for page in sorted(output_dir.rglob("*.html")):
        parser = LocalReferenceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for tag, attribute, reference in parser.references:
            try:
                target = local_reference_target(page, reference)
            except AssertionError as error:
                failures.append(str(error))
                continue
            if target is None:
                continue
            if output_root not in target.parents and target != output_root:
                failures.append(f"reference escapes artifact: {page.name}: {reference}")
                continue
            if not target.exists():
                failures.append(
                    f"missing local {tag}[{attribute}] target: "
                    f"{page.relative_to(output_dir)} -> {reference}"
                )

    assert failures == []


def test_adsense_code_is_present_on_monetized_pages(output_dir):
    builder.build_public_site(output_dir)
    publisher_id = "ca-pub-2224207953863103"
    monetized_pages = {
        "index.html",
        "game.html",
        "kinoko-guide.html",
        "mementomori-guide.html",
        "township-lv60.html",
        "township-lv70.html",
        "whiteout-survival-guide.html",
        "working-heroes-guide.html",
        "tokyo-debunker-guide.html",
        "puzzles-survival-guide.html",
        "kingshot-guide.html",
    }

    for filename in monetized_pages:
        html = (output_dir / filename).read_text(encoding="utf-8")
        assert html.count(publisher_id) == 1
        assert "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js" in html
        head = html.split("</head>", 1)[0]
        assert publisher_id in head

    for filename in {"404.html", "data-status.html"}:
        html = (output_dir / filename).read_text(encoding="utf-8")
        assert publisher_id not in html



def test_every_catalog_game_has_published_guide_mapping(output_dir):
    builder.build_public_site(output_dir)

    import csv
    import re

    games = list(csv.DictReader((output_dir / "games.csv").open(encoding="utf-8", newline="")))
    guide_text = (output_dir / "site-guides.js").read_text(encoding="utf-8")

    mapped_games = set(re.findall(r'^  "([^"]+)": \\{$', guide_text, flags=re.MULTILINE))
    catalog_games = {row["name"] for row in games}

    assert mapped_games == catalog_games

    hrefs = re.findall(r'href: "([^"]+)"', guide_text)
    assert hrefs
    for href in hrefs:
        assert not href.startswith("/")
        assert (output_dir / href).is_file(), f"missing guide target: {href}"

    for game in catalog_games:
        assert f'game.html?game={game}' in (output_dir / next(
            href for href in hrefs
            if game in (output_dir / href).read_text(encoding="utf-8")
        )).read_text(encoding="utf-8")
