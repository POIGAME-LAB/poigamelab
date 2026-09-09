from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_ui_is_non_publishable_and_separate_from_verified_offers():
    site_data = (ROOT / "site-data.js").read_text(encoding="utf-8")
    game_html = (ROOT / "game.html").read_text(encoding="utf-8")

    assert "loadCoverageCandidates" in site_data
    assert "payload?.publicationAuthorized === false" in site_data
    assert "item?.publicationAuthorized === false" in site_data
    assert "payload?.firstPartyVerificationRequired === true" in site_data
    assert "item?.firstPartyVerificationRequired === true" in site_data

    assert "coverageCandidateSection" in game_html
    assert "一次情報を確認中" in game_html
    assert "最高還元やランキングには含めていません" in game_html
    assert "candidate.rewardYenHint" not in game_html

    best_offer_block = game_html.split("function updateBestOffer", 1)[1].split("function renderRewardTrends", 1)[0]
    assert "coverageCandidates" not in best_offer_block
