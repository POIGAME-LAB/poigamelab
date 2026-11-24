# 日次新規攻略 2026-11-24 REPORT

1. 実行日（JST）2026-11-24（運営者の依頼による再実行）／checkedAt：`data/new_game_monitor.json` = 2026-11-24T03:00:22Z（main 2dc4325で実測。JST 12:00）
2. 調査したゲーム数：triage 118ゲーム中、公式ページ確認30（offer_verified 29、unreadable 1）。実プレイヤー深掘り4（WaterPark Boys・勇者サバイバー・超能力学園・サバイバルアイランド）
3. 完成記事数：**1本**（目標5本。基準を満たした分のみ）
4. 記事：ウォーターパークボーイズ ポイ活攻略｜Stage2 Open（2時間前後）の実例と進め方（WaterPark Boys）
5. 出典確認：Moppy×2・App Store・Google Play・ブログ等、当日HTTP 200（担当エージェント確認）。sarakimt.co.jp は環境のドメイン制限で取得不可・不使用
6. 保留：勇者サバイバー（条件に合う記録なし）、超能力学園（別条件のみ）、サバイバルアイランド（記録が365日超）。他 offer_verified 25件は未深掘り。Warau 209434/209435・Amefuri 131762 は解析不可で金額に不使用
7. Draft PR：作成後に記載
8. テスト：`build_daily_guides.py --check` ok／指定10テストファイルは tests/test_daily_guides.py の Warau専用だった1検査をモッピー案件に対応させて通過（検査内容は維持）
9. 未確認：実機プレイ・ポイント付与・iPhone Safari実機。ほとんどの投稿者のOS・課金状況は不明。triageの `promising=0` の意味（verified 29なのに0）は未解明
10. 次回：WaterPark Boysは公開前に `--recheck`。Moppy単一条件は口コミ0件が多く、記録のあるゲームを先に探す。

## 12時台の stale_input 判定のずれについて
実測：今回 main 2dc4325 の checkedAt は 2026-11-24T03:00:22Z。0fba5ff 時点の 02:53:04Z（JST 11:53）も当日JSTで、日付基準では stale にならない。`candidates.json` は今回 status=ok。当時の判定理由は、その実行のログがなく**原因は未確認**（推測：パーサ修正PR #360/#361 前のスクリプトが別の入力〈キュー側checkedAtや件数〉で止めた可能性）。
