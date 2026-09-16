from pathlib import Path

from scripts.inject_static_index_fallback import inject_static_fallback


ROOT = Path(__file__).resolve().parents[1]


def test_static_index_fallback_preserves_existing_page_and_adds_catalog(tmp_path):
    site = tmp_path / "_site"
    (site / "data").mkdir(parents=True)

    source_index = (ROOT / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(source_index, encoding="utf-8")
    (site / "games.csv").write_text((ROOT / "games.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (site / "data" / "published_offers.csv").write_text(
        (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    before_adsense = source_index.count("ca-pub-2224207953863103")
    summary = inject_static_fallback(
        site / "index.html",
        site / "games.csv",
        site / "data" / "published_offers.csv",
    )
    built = (site / "index.html").read_text(encoding="utf-8")

    assert summary["gameCount"] > 0
    assert 'data-static-fallback="1"' in built
    assert "POIGAME_STATIC_INDEX_FALLBACK_V1" in built
    assert "Township" in built
    assert "きのこ伝説" in built
    assert '<strong id="statGameCount">-- 件</strong>' not in built
    assert "let catalogLoaded = false;" in built
    assert "catalogLoaded = true;" in built
    assert "if (!catalogLoaded && gameGrid.querySelector('[data-static-fallback=\"1\"]'))" in built
    assert built.count("ca-pub-2224207953863103") == before_adsense
    assert '<link rel="canonical" href="https://poigamelab.com/">' in built


def test_static_index_fallback_is_idempotent(tmp_path):
    site = tmp_path / "_site"
    (site / "data").mkdir(parents=True)
    (site / "index.html").write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    (site / "games.csv").write_text((ROOT / "games.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (site / "data" / "published_offers.csv").write_text(
        (ROOT / "data" / "published_offers.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    inject_static_fallback(site / "index.html", site / "games.csv", site / "data" / "published_offers.csv")
    first = (site / "index.html").read_text(encoding="utf-8")
    result = inject_static_fallback(site / "index.html", site / "games.csv", site / "data" / "published_offers.csv")
    second = (site / "index.html").read_text(encoding="utf-8")

    assert result == {"alreadyPatched": True}
    assert second == first
