import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("probe_v45", ROOT / "scripts" / "firecrawl_township_probe.py")
probe = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(probe)


def source():
    return {"id":"coincome","name":"COINCOME","start_url":"https://cimcome.jp/","search_domains":["cimcome.jp"],"direct_listing_urls":[],"direct_detail_url_hints":["/campaigns/details/"]}


def test_tavily_no_results_is_completed_but_not_authoritative_absence():
    probe.CURRENT_TARGET = {"game":"ホワイトアウト・サバイバル"}
    c, d = probe.tavily_official_detail_discovery(source(), ["ホワイトアウト・サバイバル"], api_key="x", searcher=lambda q:{"results":[]})
    assert c == []
    assert d["searchCompleted"] is True
    assert d["confirmed"] == 0
    assert d["absenceAuthoritative"] is False
    assert d["coverage"] == "indexed_public_official_details"


def test_tavily_search_failure_is_not_clean_completion():
    probe.CURRENT_TARGET = {"game":"ホワイトアウト・サバイバル"}
    def boom(q): raise RuntimeError("network down")
    c, d = probe.tavily_official_detail_discovery(source(), ["ホワイトアウト・サバイバル"], api_key="x", searcher=boom)
    assert c == []
    assert d["searchCompleted"] is False
    assert "error" in d


def test_eligible_detail_fetch_failure_is_recorded_fail_closed():
    probe.CURRENT_TARGET = {"game":"ホワイトアウト・サバイバル"}
    s=source()
    def search(q): return {"results":[{"url":"https://cimcome.jp/campaigns/details/9999"}]}
    def fetch(url, src): raise RuntimeError("detail blocked")
    c,d=probe.tavily_official_detail_discovery(s,["ホワイトアウト・サバイバル"],api_key="x",searcher=search,fetcher=fetch)
    assert c == [] and d["searchCompleted"] is True
    assert d["eligibleUrls"] == 1
    assert d["details"][0]["ok"] is False


def test_completeness_still_fails_on_real_search_failure():
    ok,reasons=probe.assess_collection_completeness([{"source_id":"coincome","search":{"ok":False}}])
    assert ok is False and "coincome:search_failed" in reasons


def test_clean_skipped_search_does_not_create_false_negative_reason():
    ok,reasons=probe.assess_collection_completeness([{"source_id":"coincome","mode":"indexed_official_no_match","indexed_official":{"searchCompleted":True,"absenceAuthoritative":False},"search":{"skipped":True}}])
    assert ok is True and reasons == []

def test_collector_stops_before_firecrawl_after_clean_indexed_pass(monkeypatch):
    cfg={"target":{"game":"X","aliases":["X"]},"sources":[{"id":"coincome","name":"COINCOME","enabled":True,"prefer_known_pages":False,"known_target_urls":[],"direct_listing_urls":[],"start_url":"https://cimcome.jp/","search_domains":["cimcome.jp"]}]}
    monkeypatch.setattr(probe,"probe_known_pages",lambda key,src,aliases:([],[]))
    monkeypatch.setattr(probe,"direct_first_party_collect",lambda src,aliases,cfg:([],{"attempted":False,"allListingsFetched":False,"details":[]}))
    monkeypatch.setattr(probe,"tavily_official_detail_discovery",lambda src,aliases:([],{"attempted":True,"searchCompleted":True,"details":[],"absenceAuthoritative":False}))
    monkeypatch.setattr(probe,"direct_scrape",lambda *a,**k: (_ for _ in ()).throw(AssertionError("Firecrawl fallback must not run")))
    monkeypatch.setattr(probe,"domain_search",lambda *a,**k: (_ for _ in ()).throw(AssertionError("Firecrawl search must not run")))
    candidates, diagnostics=probe.collect_firecrawl("fake-firecrawl",cfg)
    assert candidates == []
    assert diagnostics[0]["mode"] == "indexed_official_no_match"
    ok,reasons=probe.assess_collection_completeness(diagnostics)
    assert ok is True and reasons == []
