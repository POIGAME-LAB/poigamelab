# Claude向け実装指示：Domino Dreams

## 対象

- 原稿：domino-dreams/article.md。完成原稿であり公開済みではない。
- 想定ページ：/domino-dreams-guide.html。canonicalはmetadata.jsonを参照。
- 案件表の正本：metadata.jsonのoffer.steps。現在のワラウ案件に限定。
- 実例：experiences.json。sources.jsonの根拠と突き合わせる。

## 実装

1. 最新mainで同名・別slug・未マージPRとの重複を再確認。調査時mainはd721371。
2. kinoko-guide.htmlのヘッダー、コンテキストバー、ヒーロー直下目次、白カード、warning/key、コンパクトsources、フッターを再利用。
3. assets/guide-experience.css/jsとexperience-panelを使用。experiences.jsonをdata/guide-experiences/domino-dreams.jsonへ。追加の監査用キーを削る場合も元データは維持。
4. 日数不明はnullのまま。現在実例対象外の記録に代表日数バッジを付けない。共通表示側がnullを扱えるか確認し、0日として描画しない。
5. 本文の[A1]等は根拠ID。公開時は各根拠リンク・脚注に変換し、編集部判断のラベルを維持。本文先頭のH1をSEOタイトルとして設定し、記事内の目次をHTMLアンカーへ移植。
6. 攻略のみ追加方式。guides.html、site-researched-guides.js、sitemap.xml、build_public_site.pyの許可リストを必要分だけ更新。登録名とURLを重複させない。
7. games.csv未登録なので架空のgame.html?game=比較リンクは作らず、確認した外部案件へ案内する。published_offers.csv等への手入力は禁止。

## 画像・内部リンク

- 画像は未制作。公式画像・ロゴを無断転載しない。既存記事と同様の文字主体ヒーローで実装可能。公開面へ「画像準備中」等を出さない。
- 攻略一覧へのリンクを設置。関連攻略リンクは実在確認後に追加。未公開PR #344の3記事へは未公開状態のままリンクしない。

## 再検証・未確認

- 当日の公開本文は直接取得したが、広告ボタンから先の実ストアID、ログイン後の個別条件、実際のポイント付与、ユーザーの対象資格は未検証。
- 公開前に同じURLの掲載継続・全Step・OS・期限・支出額を再取得。古い表示額を本日の確定額にしない。
- PC/スマホの目次・表・実例タイムライン、内部リンク・canonical・SEO・JSON-LDを確認。共通JSON-LDで架空レビュー評価を作らない。
- 既存テスト・公開ビルドを実行し、新旧失敗を分離。iPhone Safari実機は未確認と報告。
- PR・push・マージ・本番公開は別途ユーザーの依頼範囲で判断。今回パッケージの存在自体は公開許可ではない。
