# POIGAME LAB データ収集基盤

## 方針
「自動取得した数字を即公開」はしません。ポイント案件は条件・OS・新規/既存・ステップ条件などで数字の意味が変わるため、誤掲載を避けるために **自動収集 → 候補 → 確認 → 公開** の2段階にしています。

## 何を自動収集するか
1. **現在の案件候補**: `games.csv` × `sources.csv` を検索し、公式ドメインの検索結果から還元額候補とURLを `data/offer_candidates.csv` に保存。
2. **話題ゲーム候補**: `trend_sources.csv` に登録したXアカウントの最近の検索結果から既知ゲーム言及と新規発見候補を `data/trend_mentions.csv` に保存。
3. **攻略候補**: 「ゲーム名 ポイ活 攻略」の検索結果を `data/guide_candidates.csv` に保存。

## GitHubで自動実行
`.github/workflows/collect-data.yml` は6時間ごとに候補データを更新します。GitHub Actionsを有効にすると動きます。

## 公開方法
候補を確認後、例えば次のコマンドで案件を承認できます。

```bash
python scripts/approve_offer.py "Township" coincome 10500 "https://..."
```

承認されたものだけ `offers.csv` に `verified=true` として入ります。

## 重要
- `url` は利用者が押すリンク。将来アフィリエイトリンクを取得したらここに入れます。
- `sourceUrl` は金額確認に使った根拠ページ。
- 既存の金額は開発用データなので、今回 `verified=false` にしています。
- Xは公式APIなしでは取得が不安定なため、検索インデックス経由の「候補収集」に留めます。
- メルカリのポイントミッションはアプリ内表示が中心なので、完全自動化より「候補＋確認」の運用が安全です。
