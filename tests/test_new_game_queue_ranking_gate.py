import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import write_new_game_content_queue as queue
from tests.test_new_game_content_queue import report


def test_group_budget_limit_emits_empty_safe_handoff():
    value = report()
    value["groupLimitReached"] = True
    value["rankingComplete"] = False
    out = queue.build(value)
    assert out["count"] == 0
    assert out["items"] == []
    assert out["rankingComplete"] is False
    assert out["holdReason"] == "ranking_group_budget_reached"
    assert out["publicationAuthorized"] is False


def test_detail_budget_limit_emits_empty_safe_handoff():
    value = report()
    value["detailLimitReached"] = True
    value["rankingComplete"] = False
    out = queue.build(value)
    assert out["count"] == 0
    assert out["items"] == []
    assert out["holdReason"] == "ranking_detail_budget_reached"


def test_complete_ranking_retains_top_five():
    value = copy.deepcopy(report())
    value["rankingComplete"] = True
    value["groupLimitReached"] = False
    value["detailLimitReached"] = False
    out = queue.build(value)
    assert out["count"] == 5
    assert out["rankingComplete"] is True
    assert out["holdReason"] is None
