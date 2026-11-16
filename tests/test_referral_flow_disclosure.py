"""Regression checks for registration referral vs public offer link UX.

These are static contract checks: account ownership and actual referral attribution
must be verified in the point-site dashboards, not inferred from HTML.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_homepage_explains_referral_before_offer_navigation():
    html = read("index.html")
    assert 'class="referral-flow-guide"' in html
    assert "「最高還元サイトへ」はゲーム案件の確認用です" in html
    assert "「このサイトに登録［PR］」や紹介コード" in html
    assert "const safeReferralUrl = referral" in html
    assert "POIGAME_DATA.safeHttpUrl(bestOffer.url)" in html
    assert 'rel="sponsored noopener noreferrer"' in html


def test_game_detail_distinguishes_registration_from_offer_link():
    html = read("game.html")
    assert 'class="referral-flow-guide"' in html
    assert "「案件を見る」はゲーム案件を確認するリンク" in html
    assert "案件リンクと［PR］の違い" in html
    assert "const safeUrl = POIGAME_DATA.safeHttpUrl(offer.url)" in html
    assert "POIGAME_DATA.safeHttpUrl(referral.url)" in html
    assert 'rel="sponsored noopener noreferrer"' in html
    assert "サイト登録のみ［PR］" in html


def test_policy_describes_separate_purposes_without_guaranteeing_commissions():
    html = read("about.html")
    assert "案件の確認用リンク" in html
    assert "新規会員登録用紹介リンク" in html
    assert "保証されません" in html


def test_referral_registry_preserves_provider_issued_urls_and_codes():
    js = read("site-referrals.js")
    assert "window.POIGAME_REFERRALS" in js
    assert 'warau: Object.freeze({' in js
    assert 'mikoshi: Object.freeze({' in js
    assert 'url: "",' in js  # Code-only provider stays code-only.
    # Never infer that a provider's registration page code must equal the
    # suffix of its invitation URL: Warau's help explicitly allows a mismatch.
