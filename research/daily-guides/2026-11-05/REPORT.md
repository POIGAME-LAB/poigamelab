# 2026-11-05 日次新規攻略｜結果報告（初回手動テスト）

目標最大5本に対し、**完成1本**。品質基準を満たさない候補で本数を水増ししていません。

## 1. 実行日・取得データ

- 実行日：2026年11月5日（JST）。Routine導入前の初回手動テスト（Claude Code）。
- 使用データ：`data/new_game_content_queue.json` と `data/new_game_monitor.json`。どちらも checkedAt 2026-11-04T21:56:46Z（＝2026-11-05 06:56 JST）で当日のデータ。main 23df481。
- 候補整理：`candidates.json`。当日データの164候補（既掲載・未マージPR・カタログ17件、非ゲーム17件、案件集合サービス2件などを除外）。

## 2〜4. 調査数・完成記事

- 判断を記録した候補：29件（うち詳細を調べた候補25件）。詳細は `selection.json`。
- 完成：1本

| ゲーム | タイトル | ページ |
| --- | --- | --- |
| ミステリータウン：マージゲーム（Mystery Town） | ミステリータウン ポイ活攻略｜レベル120・150の実例と30日・60日の進め方 | /mystery-town-guide.html |

## 5. 出典の確認状況

- ワラウ iOS 206151／Android 206152：当日直接取得（HTTP 200）。全Step・合計（11,040／11,550pt）の一致を確認。どちらも**2026年11月07日までの増額表示**（増額前 10,510／11,000pt）で、記事に明記。証拠：`evidence/mystery-town-offers.json`（SHA-256つき）。
- App Store（id6503603603）・Google Play（com.cedargames.mysterytown）：開発元 Cedar Games Studio、案件ページの広告主と一致。
- 実例：ワラウ口コミ（2026年4〜10月、58件のうち到達日数・レベルの記載がある投稿）と個人ブログ1件。実例パネルに7名、すべて365日以内。日数の記載がないものは推定していない。
- 出典URL 7件すべて当日 HTTP 200。

## 6. 保留・除外（主なもの）

| 候補 | 判定 | 理由 |
| --- | --- | --- |
| ベガス クレイズ カジノ | 保留 | ワラウの公開ページが表示不可。10/31の保留理由（独立した到達記録不足）も未解消 |
| Fish of Fortune／MONOPOLY GO!／ジャックポットワールド ほかモッピー案件 | 保留 | モッピー公開ページは合計額のみで全Stepの内訳が見えない |
| モンスターサバイバル | 保留 | 全15Step・37,500ptは確認。2026年7月配信・案件は当日新規で、日付つきの到達記録なし |
| 小森の宿-ららら | 保留 | 案件・口コミは確認。公式ストアでアプリを同定できない |
| Z ルート／Endless Arrow／アツアツ冒険伝 ほか | 保留 | ワラウの公開ページが「表示できません」 |
| Shelf Sort／Happy Chef Mania／Monster Hunter Outlanders | 保留 | 案件は確認。口コミ0件・到達記録なし |
| TikTok／TikTok Lite／Pococha／TIPSTAR | 除外 | ゲーム攻略の対象外 |
| Freecash | 除外 | 案件集合サービス |
| ザ・グランドマフィア／Bingo Blitz／Heroes vs Crazy Wiggler | 除外 | 未マージPR #344 で制作済み |

## 7〜8. PR・テスト

- Draft PR：https://github.com/POIGAME-LAB/poigamelab/pull/348（セットアップと初回記事を同じPRに含む）。
- ローカル：`tests/test_daily_guides.py` 19件合格（改ざん検出の否定テストを含む）。関連する攻略テストも合格。全体 pytest は main 62件失敗／1426件合格、ブランチ 62件失敗／1445件合格で、新規失敗0件（失敗はいずれも main に元からあるもの）。
- 表示：Playwright（PC 1280px／iPhone 13／360px）で横スクロール0、目次11リンク解決、実例7名表示、攻略一覧に1件。
- GitHub CI（PR #348、HEAD ed674cc）：validate／validate-guides／validate-player-progress／validate-township-guide／validate-r2 の5件すべて success。なお `tests/test_daily_guides.py` は既存のCIワークフローに含まれていない（Actionsは変更していない）ため、CIでは実行されていない。
- 定期実行：Routineはこの環境からの登録が権限判定で拒否されたため未登録。設定値とプロンプトは docs/daily-guide-routine.md。

## 9. 未確認事項

- 当サイトは実機でプレイしていない。ログイン後の表示・実際のポイント付与は未確認。
- Android課金Stepのパック価格（案件ページに記載なし）。
- 増額期間終了後（11月8日以降）の各Stepの額。
- iPhone Safari実機での表示。

## 10. 次回への注意点

- 11月8日以降に公開する場合は、ミステリータウンの案件ページを再取得し、増額終了後の表とFAQを更新する。
- モッピー単独の高額案件は全Stepが公開ページにないため、毎日上位に出ても保留が続く。別サイトで同じゲームの全Stepが出たら再評価する。
- 当日スキャンの全件は R2 にあり、Routineから読めるのは公開モニターの表示範囲のみ。
