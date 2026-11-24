"""Per-site diagnostics printed to the daily Actions log (counts and internal codes only)."""
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct  # noqa: E402


def test_counts_fetch_errors_detail_states_and_review_reasons_without_urls_or_text():
    cache = {
        ("kurashiru_reward", "https://www.rewards.kurashiru.com/categories/3?page=1"):
            (None, HTTPError("https://x", 403, "Forbidden", {}, None)),
        ("nifty_point", "https://api.point.nifty.com/service/alist/spapp"): (None, URLError("boom")),
        ("moppy", "https://pc.moppy.jp/a"): (("<html>", "https://pc.moppy.jp/a"), None),
    }
    snapshots = [
        {"source": "moppy", "sourceEvidence": {"state": "parsed"}},
        {"source": "moppy", "sourceEvidence": {"state": "review_required", "reason": "missing_or_ambiguous_current_reward"}},
        {"source": "hapitas", "sourceEvidence": {"state": "review_required", "reason": "タイトル <b>キングショット</b> https://hapitas.jp/x"}},
        "junk",
    ]
    review = [
        {"source": "amefuri", "reason": "discovery_required", "url": "https://www.amefri.net/x"},
        {"source": "amefuri", "reason": "first_party_coverage_fetch_failed", "error": "http_status_503"},
    ]
    out = direct.source_diagnostics(review, snapshots, cache)
    assert out["kurashiru_reward"]["fetchErrors"] == {"http_status_403": 1}
    assert out["nifty_point"]["fetchErrors"] == {"network_error": 1}
    assert out["moppy"]["detailStates"] == {"parsed": 1, "review_required:missing_or_ambiguous_current_reward": 1}
    assert out["amefuri"]["reviewReasons"] == {"discovery_required": 1, "first_party_coverage_fetch_failed:http_status_503": 1}
    text = str(out)
    assert "http" not in text.replace("http_status", "") and "キングショット" not in text and "<" not in text


def test_empty_inputs():
    assert direct.source_diagnostics(None, None, None) == {}
