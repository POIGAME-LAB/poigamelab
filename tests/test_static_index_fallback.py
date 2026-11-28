from pathlib import Path

from scripts.inject_static_index_fallback import inject_static_fallback


ROOT = Path(__file__).resolve().parents[1]


def test_static_index_fallback_preserves_existing_page_and_adds_catalog(tmp_path):
    site = tmp_path / "_site"
    site.mkdir(parents=True)

    source_index = (ROOT / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(source_index, encoding="utf-8")
    (site / "games.csv").write_text((ROOT / "games.csv").read_text(encoding="utf-8"), encoding="utf-8")

    before_adsense = source_index.count("ca-pub-2224207953863103")
    summary = inject_static_fallback(site / "index.html", site / "games.csv")
    built = (site / "index.html").read_text(encoding="utf-8")

    assert summary["gameCount"] > 0
    assert 'data-static-fallback="1"' in built
    assert "POIGAME_STATIC_INDEX_FALLBACK_V1" in built
    assert "Township" in built
    assert "きのこ伝説" in built
    assert '<strong id="statGameCount">-- 件</strong>' not in built
    assert "let catalogLoaded = false;" in built
    assert "catalogLoaded = true;" in built
    assert 'if (!catalogLoaded && gameGrid.querySelector(\'[data-static-fallback="1"]\'))' in built
    assert built.count("ca-pub-2224207953863103") == before_adsense
    assert '<link rel="canonical" href="https://poigamelab.com/">' in built


def test_static_index_fallback_is_idempotent(tmp_path):
    site = tmp_path / "_site"
    site.mkdir(parents=True)
    (site / "index.html").write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    (site / "games.csv").write_text((ROOT / "games.csv").read_text(encoding="utf-8"), encoding="utf-8")

    inject_static_fallback(site / "index.html", site / "games.csv")
    first = (site / "index.html").read_text(encoding="utf-8")
    result = inject_static_fallback(site / "index.html", site / "games.csv")
    second = (site / "index.html").read_text(encoding="utf-8")

    assert result == {"alreadyPatched": True}
    assert second == first


# ---------------------------------------------------------------- 7-day rule in the no-JS first HTML (matches site-data.js)
import json
from datetime import date

from scripts.inject_static_index_fallback import _read_verified_offers

HEADER = "offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified"
TODAY = date(2026, 11, 25)


def _csv(tmp_path, rows, policy=None):
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    lines = [HEADER] + [f"k{i},{g},warau,,{r},x,iOS,通常,,{d},https://a.test/,https://a.test/,true" for i, (g, r, d) in enumerate(rows)]
    path = tmp_path / "data" / "published_offers.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if policy is not None:
        (tmp_path / "config" / "refresh_policy.json").write_text(json.dumps(policy), encoding="utf-8")
    return path


def test_static_fallback_hides_rows_not_reconfirmed_for_more_than_7_days(tmp_path):
    path = _csv(tmp_path, [("A", 100, "2026-11-25"), ("B", 200, "2026-11-18"), ("C", 300, "2026-11-17"), ("D", 400, "2026-09-28")])
    assert [o["game"] for o in _read_verified_offers(path, TODAY)] == ["A", "B"]  # exactly 7 days old is still shown


def test_static_fallback_never_trusts_a_future_or_missing_date(tmp_path):
    path = _csv(tmp_path, [("A", 100, "2026-12-31"), ("B", 200, "")])
    assert _read_verified_offers(path, TODAY) == []  # read, nothing may be shown - not "unknown" (None)


def test_static_fallback_keeps_none_for_a_missing_file(tmp_path):
    assert _read_verified_offers(tmp_path / "data" / "published_offers.csv", TODAY) is None


def test_static_fallback_follows_the_policy_file_like_site_data_js(tmp_path):
    rows = [("A", 100, "2026-11-25"), ("B", 200, "2026-11-22"), ("C", 300, "2026-11-10")]
    path = _csv(tmp_path, rows, policy={"publication": {"maxOfferAgeDays": 3}})
    assert [o["game"] for o in _read_verified_offers(path, TODAY)] == ["A", "B"]
    path2 = _csv(tmp_path / "x", rows) if (tmp_path / "x").mkdir() is None else None
    assert [o["game"] for o in _read_verified_offers(path2, TODAY)] == ["A", "B"]  # no policy file -> 7
