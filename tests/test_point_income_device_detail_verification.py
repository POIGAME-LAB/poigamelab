import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify-point-income-device-details.py"
PUBLISH = ROOT / "scripts" / "publish-point-income-device-offers.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def aliases():
    return {
        "エバーテイル": ["エバーテイル", "evertale"],
        "Township": ["township", "タウンシップ"],
    }


def direct_detail():
    return {
        "adId": "149940",
        "gameHint": "エバーテイル",
        "url": "https://sp.pointi.jp/ad/149940/",
        "finalUrl": "https://sp.pointi.jp/ad/149940/",
        "listingTitle": "エバーテイル（Android用）【高還元】",
        "listingPlatform": "Android",
        "listingCurrentPoints": 2500,
        "pageTitle": "エバーテイル（Android用）【高還元】の詳細｜ポイントインカム",
        "headings": ["エバーテイル（Android用）【高還元】", "成果条件", "ポイント獲得条件"],
        "leadText": (
            "エバーテイル（Android用）【高還元】 1,800pt ⇒ 2,500pt (250円分) 紹介する "
            "成果条件 詳細 成果条件 アプリインストール＋起動→承認待ち反映後、10日以内に3日連続でログインボーナス獲得 "
            "ポイント獲得条件 初回利用のみ。ご注意事項。下記の場合はポイント追加の対象外となります。"
            "過去利用、海外IP、重複利用は対象外です。広告IDリセットも対象外です。"
            "追加の注意事項を確認してください。" + ("対象外条件と注意事項を確認してください。" * 30)
            + " ポイントに関するお問い合わせについて "
            "広告主へ直接お問い合わせすることは禁止しております。ポイントインカムサポートセンターへお願いします。"
        ),
        "keywordSnippets": [
            "広告主へ直接お問い合わせすることは禁止しております。ポイントインカムサポートセンターへお願いします。"
        ],
    }


def offer():
    return {
        "adId": "149940",
        "url": "https://sp.pointi.jp/ad/149940/",
        "title": "エバーテイル（Android用）【高還元】",
        "platform": "Android",
        "currentPoints": 2500,
    }


def test_direct_first_party_terms_are_authorized():
    verify = load(VERIFY, "verify_pi")
    item = verify.review_item(direct_detail(), {"149940": offer()}, aliases())
    assert item["state"] == "parsed"
    assert item["publicationAuthorized"] is True
    assert item["downstreamTermsRequired"] is False
    assert item["verifiedCurrentRewardYen"] == 250
    assert item["deadline"] == "承認待ち反映後、10日以内"


def test_downstream_authority_stays_candidate_only():
    verify = load(VERIFY, "verify_pi_downstream")
    detail = direct_detail()
    detail["adId"] = "156226"
    detail["url"] = detail["finalUrl"] = "https://sp.pointi.jp/ad/156226/"
    detail["listingTitle"] = "タウンシップ【アプリ利用でptゲット/iOS用】"
    detail["listingPlatform"] = "iOS"
    detail["listingCurrentPoints"] = 308302
    detail["pageTitle"] = detail["listingTitle"] + "の詳細｜ポイントインカム"
    detail["headings"][0] = detail["listingTitle"]
    detail["gameHint"] = "Township"
    detail["leadText"] = (
        detail["listingTitle"] + " 308,302pt (30,830円分) 紹介する "
        "成果条件 詳細 成果条件 アプリインストール後、遷移先ページに記載の条件達成 "
        "ポイント獲得条件 本ページに記載のポイント数と、遷移先ページに記載されているポイント数が異なる場合がございます。"
        "その場合は、遷移先ページに記載のポイント数が適用となります。対象外条件もあります。"
        "その他詳細は遷移先ページ「アプリ利用でポイントGET!」内の条件をご確認ください。"
        + ("対象外条件と注意事項を確認してください。" * 30)
        + "ポイントに関するお問い合わせについて 広告主へ直接お問い合わせすることは禁止しております。"
        "ポイントインカムサポートセンターへお願いします。"
    )
    off = {
        "adId": "156226", "url": detail["url"], "title": detail["listingTitle"],
        "platform": "iOS", "currentPoints": 308302,
    }
    item = verify.review_item(detail, {"156226": off}, aliases())
    assert item["state"] == "parsed"
    assert item["publicationAuthorized"] is False
    assert item["candidateOnly"] is True
    assert item["downstreamTermsRequired"] is True
    assert item["verifiedCurrentRewardYen"] == 30830.2
    assert item["displayedCurrentRewardYenFloor"] == 30830


def test_reward_mismatch_fails_closed():
    verify = load(VERIFY, "verify_pi_bad")
    detail = direct_detail()
    detail["leadText"] = detail["leadText"].replace("2,500pt (250円分)", "2,600pt (260円分)")
    item = verify.review_item(detail, {"149940": offer()}, aliases())
    assert item["state"] == "review_required"
    assert item["reason"] == "detail_reward_mismatch"
    assert item["publicationAuthorized"] is False


def test_publisher_only_upserts_authorized_rows(tmp_path):
    publisher = load(PUBLISH, "publish_pi")
    out = tmp_path / "published.csv"
    out.write_text(
        "offerKey,game,site,provider,reward,condition,platform,type,deadline,updatedAt,url,sourceUrl,verified\n"
        "Other|warau|iOS|https://example.test/,Other,warau,,100,x,iOS,通常,x,2026-09-01,https://example.test/,https://example.test/,true\n",
        encoding="utf-8",
    )
    authorized = {
        "state": "parsed", "publicationAuthorized": True, "candidateOnly": False,
        "downstreamTermsRequired": False, "game": "エバーテイル", "platform": "Android",
        "url": "https://sp.pointi.jp/ad/149940/", "verifiedCurrentRewardYen": 250,
        "conditionText": "10日以内に3日連続ログイン", "deadline": "10日以内",
    }
    blocked = dict(authorized)
    blocked.update({
        "url": "https://sp.pointi.jp/ad/156226/",
        "publicationAuthorized": False,
        "candidateOnly": True,
        "downstreamTermsRequired": True,
    })
    rows = publisher.publish({
        "phase": "POINT_INCOME_DEVICE_DETAIL_REVIEW_V1",
        "items": [authorized, blocked],
    }, out, updated_at="2026-09-26")
    assert len(rows) == 1
    value = out.read_text(encoding="utf-8")
    assert "point_income" in value
    assert "149940" in value
    assert "156226" not in value
    assert "Other|warau" in value
