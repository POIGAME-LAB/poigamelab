import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
RATES = ROOT / "config" / "point_value_rates.json"
SOURCES = ROOT / "config" / "point_sources.json"
def load(): return json.loads(RATES.read_text(encoding="utf-8"))
def test_every_point_source_has_explicit_rate_policy():
    rates=load()["sources"]; sources=json.loads(SOURCES.read_text(encoding="utf-8"))["sources"]
    assert {s["id"] for s in sources} == set(rates)
def test_known_different_scales_are_not_flattened_to_raw_numbers():
    r=load()["sources"]; assert r["moppy"]["pointsPerYen"]==1; assert r["amefuri"]["pointsPerYen"]==10; assert r["ec_navi"]["pointsPerYen"]==10; assert r["kurashiru_reward"]["pointsPerYen"]==100; assert r["trima"]["pointsPerYen"]==100
def test_chobirich_uses_current_2026_rate_not_historical_rate():
    r=load()["sources"]["chobirich"]; assert r["pointsPerYen"]==1; assert r["effectiveFrom"]=="2026-06-22"; assert "historical 2pt=1JPY" in r["note"]
def test_unknown_rates_fail_closed():
    r=load()["sources"]
    for sid in ("mikoshi","point_income","gmo_point","powl"): assert r[sid]["status"]=="unsupported" and r[sid]["yenPerPoint"] is None
def test_direct_yen_sources_do_not_infer_raw_point_rate():
    r=load()["sources"]
    for sid in ("coincome","gendama"): assert r[sid]["status"]=="direct_yen_equivalent_only" and r[sid]["yenPerPoint"] is None
def test_verified_rate_rows_have_first_party_evidence():
    for r in load()["sources"].values():
        if r["status"].startswith("verified"): assert r["evidenceUrl"] and r["evidenceUrl"].startswith("https://")
def test_mixed_scale_face_values_sort_correctly_after_conversion():
    r=load()["sources"]; raw=[("moppy",900),("amefuri",12000),("kurashiru_reward",150000),("ec_navi",11000)]
    converted=[(p/r[s]["pointsPerYen"],s) for s,p in raw]
    assert [s for _,s in sorted(converted,reverse=True)]==["kurashiru_reward","amefuri","ec_navi","moppy"]
