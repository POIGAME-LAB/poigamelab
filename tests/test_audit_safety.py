"""Audit regressions. HTML below is synthetic, NOT captured Hapitas DOM."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_scan_review as daily
import structured_publication as publication


@pytest.mark.parametrize("name", ["LUCK ROCK", "Sea Block 1010", "さる山温泉旅館",
                                  "インポッシブルカート", "カプとれ", "クラウドキャッチャー"])
@pytest.mark.parametrize("campaign", [33000, 777, 120000])
def test_legacy_hapitas_text_interval_cannot_certify_reward(name, campaign):
    url = "https://hapitas.jp/item/detail/itemid/12345"
    raw = f'''<html><head><title>{name}</title></head><body>
    <h1>{name} Android</h1><aside>紹介特典 {campaign}pt</aside>
    <section>案件報酬 105pt</section><div>ポイント対象条件
    ポイント獲得条件 新規インストール後に起動 成果受付期限 30日以内
    ハピタスご利用前に必ずご確認ください</div><footer>1ポイント=1円</footer>
    </body></html>'''
    evidence = daily.direct.inspect_hapitas_offer(raw, url, url, [name])
    # Demonstrates the remaining defect without accepting it as verification.
    assert evidence["verifiedCurrentRewardPoints"] == campaign
    assert daily.explicit_yen(evidence) is None


@pytest.mark.parametrize("placement", ["top", "nested", "candidate_only"])
def test_explicit_nonpublication_input_preserves_existing_row(placement):
    row = {"offerKey": "existing", "game": "Example", "site": "warau",
           "url": "https://www.warau.jp/contents/point/pointEntrance.php?point_id=123",
           "reward": "100", "verified": "true", "type": "StepUp"}
    item = {"game": row["game"], "source": "warau", "url": row["url"],
            "sourceEvidence": {"state": "parsed"}}
    if placement == "top":
        item["publicationAuthorized"] = False
    elif placement == "nested":
        item["sourceEvidence"]["publicationAuthorized"] = False
    else:
        item["candidateOnly"] = True
    before = copy.deepcopy(row)
    out, report = publication.prepare([row], [item], {"warau": {"id": "warau"}},
                                      "2026-09-22T12:00:00Z",
                                      {"enabled": True, "sources": ["warau"]}, True)
    assert out == [before] and row == before
    assert report["updatedRows"] == 0
    assert report["decisions"][0]["holdReason"] == "no_current_evidence"
