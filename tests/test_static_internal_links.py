"""Phase 1: internal links must exist in the first HTML (before any JavaScript runs)."""
import csv
import re
import subprocess
from urllib.parse import quote, unquote
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ["index.html", "offers.html", "guides.html", "about.html", "privacy.html", "contact.html"]
SHARED_HEADER = ["index.html", "offers.html", "guides.html", "about.html", "privacy.html", "contact.html", "game.html"]


def hrefs(text):
    return set(re.findall(r'href="([^"]+)"', text))


def test_header_placeholder_has_plain_links():
    for name in SHARED_HEADER + [p.name for p in ROOT.glob("*-guide.html")] + ["township-lv70.html"]:
        html = (ROOT / name).read_text(encoding="utf-8")
        m = re.search(r"<div data-poigame-header>(.*?)</div>", html, re.S)
        assert m, name
        links = hrefs(m.group(1))
        assert {"index.html", "offers.html", "guides.html", "about.html", "contact.html"} <= links, name


def test_footer_fallback_has_all_core_links_and_is_replaced_by_js():
    footer_js = (ROOT / "site-footer.js").read_text(encoding="utf-8")
    assert "[data-poigame-footer-fallback]" in footer_js
    for name in ["index.html", "offers.html", "guides.html", "about.html", "privacy.html", "contact.html", "kinoko-guide.html"]:
        html = (ROOT / name).read_text(encoding="utf-8")
        m = re.search(r"<footer data-poigame-footer-fallback>(.*?)</footer>", html, re.S)
        assert m, name
        assert set(CORE) <= hrefs(m.group(1)), name


def test_guides_hub_lists_every_published_guide_in_first_html():
    html = (ROOT / "guides.html").read_text(encoding="utf-8")
    block = html.split("<!-- POIGAME_STATIC_GUIDE_LINKS_START -->")[1].split("<!-- POIGAME_STATIC_GUIDE_LINKS_END -->")[0]
    linked = hrefs(block)
    for page in ROOT.glob("*-guide.html"):
        assert page.name in linked, page.name
    assert "township-lv70.html" in linked
    assert 'grid.replaceChildren()' in html  # no duplicate cards when JS runs


def test_static_guide_links_are_in_sync_with_guide_registries():
    result = subprocess.run(["node", "scripts/sync_static_guide_links.js", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_sitemap_lists_every_guide_page_and_core_pages():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    for page in list(ROOT.glob("*-guide.html")) + [ROOT / "township-lv70.html"]:
        assert f"https://poigamelab.com/{page.name}</loc>" in sitemap, page.name
    for name in ["about.html", "contact.html", "guides.html", "offers.html", "privacy.html"]:
        assert f"https://poigamelab.com/{name}</loc>" in sitemap
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    assert len(locs) == len(set(locs))


def _encode_uri_component(value):
    # Same unreserved set as JavaScript's encodeURIComponent.
    return quote(value, safe="-_.!~*'()")


def _sitemap_game_locs():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    return [loc for loc in re.findall(r"<loc>([^<]+)</loc>", sitemap) if "game.html" in loc]


def test_sitemap_game_detail_urls_are_the_urls_the_site_links_to_and_canonicalises_to():
    """Sitemap, internal links and the JS canonical must all name the same game URL.

    One-directional on purpose: a catalog game that is not (yet) listed is not an error, but a
    listed URL must be a real catalog game written exactly like the internal links.
    """
    prefix = "https://poigamelab.com/game.html?game="
    with (ROOT / "games.csv").open(encoding="utf-8-sig", newline="") as handle:
        catalog = {row["name"].strip() for row in csv.DictReader(handle) if row.get("name", "").strip()}
    locs = _sitemap_game_locs()
    assert locs, "game detail URLs are expected in the sitemap"
    assert len(locs) == len(set(locs))
    guides_html = (ROOT / "guides.html").read_text(encoding="utf-8")
    for loc in locs:
        assert loc.startswith(prefix), loc
        raw = loc[len(prefix):]
        assert "&" not in loc and "#" not in loc, loc
        name = unquote(raw)
        assert name in catalog, f"sitemap lists a game that is not in games.csv: {name}"
        assert raw == _encode_uri_component(name), f"not encodeURIComponent form: {loc}"
        assert f'href="game.html?game={raw}' in guides_html, f"guides.html does not link to {loc}"
    # The JS canonical is built with encodeURIComponent on the same prefix.
    game_html = (ROOT / "game.html").read_text(encoding="utf-8")
    assert "`" + prefix + "${encodeURIComponent(game.name)}`" in game_html


def test_sitemap_never_lists_the_bare_game_page():
    assert "https://poigamelab.com/game.html</loc>" not in (ROOT / "sitemap.xml").read_text(encoding="utf-8")
