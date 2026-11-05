# 日次新規攻略（research/daily-guides）

毎日の定期実行（Claude Code クラウド Routine「POIGAME LAB｜毎日新規攻略5本」）が、その日の取得データから最大5本の新規ゲーム攻略を制作するための作業フォルダです。手順の正本は [docs/daily-guide-routine.md](../../docs/daily-guide-routine.md)。

`research/` は公開ビルドの許可リスト外で、このフォルダ自体は公開されません。公開されるのは、ビルドで生成した `<slug>-guide.html` と `data/guide-experiences/<slug>.json` だけです（mainマージ後）。

## 構成

```
research/daily-guides/
  aliases.json                 編集者が同一アプリと確認した表記揺れ（似た名前の自動統合はしない）
  legacy-holds.json            Routine開始前（Notion記録）の保留。除外ではない
  <YYYY-MM-DD>/
    candidates.json            scripts/daily_guide_candidates.py の出力（当日データの候補・除外理由）
    selection.json             採用／保留／除外の判断と理由（重複防止の履歴）
    REPORT.md                  その日の結果報告
    evidence/<slug>-offers.json  scripts/daily_guide_evidence.py の当日取得記録（全Step・合計・SHA-256・口コミ索引）
    <slug>/
      article.md               完成原稿（H1＝SEOタイトル、出典ID [M1] 付き）
      metadata.json            SEO・ゲーム同定・案件表（全Step・課金フラグ・期限・合計）
      sources.json             出典（当日確認）
      experiences.json         実例パネル（日数不明はnull、0にしない）
      page.json                ヒーロー統計・案件リンク・関連攻略・一覧カード文
      spec.json                ビルド生成物（手で編集しない）
```

## コマンド

```sh
python scripts/daily_guide_candidates.py --scan-remote            # 当日候補（前日データなら status=stale_input で停止）
python scripts/daily_guide_evidence.py --slug <slug> <point_id>... --reviews 6
python scripts/build_daily_guides.py --check research/daily-guides/<date>   # 品質ゲートのみ
python scripts/build_daily_guides.py research/daily-guides/<date>           # HTML生成・攻略一覧／sitemap／ビルド許可へ登録
python -m pytest -q tests/test_daily_guides.py
```
