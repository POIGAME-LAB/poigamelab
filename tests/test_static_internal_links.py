"""Phase 1: internal links must exist in the first HTML (before any JavaScript runs)."""
import re
import subprocess
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
