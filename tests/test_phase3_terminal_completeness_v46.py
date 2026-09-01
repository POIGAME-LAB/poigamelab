import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("probe_v46", ROOT / "scripts" / "firecrawl_township_probe.py")
probe = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(probe)


def test_old_known_page_failure_is_superseded_by_indexed_verified_success():
    ok,reasons=probe.assess_collection_completeness([{
        "source_id":"moppy", "mode":"indexed_official_fast_path",
        "known_pages":[{"ok":False,"cache":"miss"}],
        "search":{"skipped":True}
    }])
    assert ok is True and reasons == []


def test_old_known_page_failure_is_superseded_by_clean_indexed_no_match():
    ok,reasons=probe.assess_collection_completeness([{
        "source_id":"coincome", "mode":"indexed_official_no_match",
        "known_pages":[{"ok":False,"cache":"miss"}],
        "search":{"skipped":True}
    }])
    assert ok is True and reasons == []


def test_known_page_failure_still_degrades_when_no_clean_terminal_state():
    ok,reasons=probe.assess_collection_completeness([{
        "source_id":"coincome", "mode":"firecrawl_unavailable",
        "known_pages":[{"ok":False,"cache":"miss"}],
        "search":{"ok":False}
    }])
    assert ok is False
    assert "coincome:known_page_miss" in reasons
    assert "coincome:search_failed" in reasons


def test_partial_known_fast_path_remains_fail_closed():
    ok,reasons=probe.assess_collection_completeness([{
        "source_id":"warau", "mode":"known_official_fast_path",
        "known_pages":[{"ok":True}],
        "search":{"skipped":True,"partialAccepted":True}
    }])
    assert ok is False and "warau:partial_known_fast_path" in reasons


def test_fatal_error_is_never_superseded_by_clean_mode_label():
    ok,reasons=probe.assess_collection_completeness([{
        "source_id":"moppy", "mode":"indexed_official_fast_path",
        "fatalError":"boom", "known_pages":[{"ok":False,"cache":"miss"}],
        "search":{"skipped":True}
    }])
    assert ok is False and "moppy:fatal" in reasons
