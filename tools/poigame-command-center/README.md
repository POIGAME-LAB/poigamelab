# POIGAME LAB COMMAND CENTER

POIGAME LAB専用の、個人用 **GA4 + Search Console 統合ダッシュボード**。

## V1

- iPhoneで1タップ起動
- 7日 / 28日切替
- GA4: Users / PV / Sessions
- Search Console: Click / Impressions / CTR / 平均順位
- 前期間比較
- 検索クエリ上位
- ページ別の Search Console × GA4 × invite_click 合体表
- `cta_location` 別の招待CTAクリック
- 自動候補
  - CTR改善候補
  - 11〜20位の追記・強化候補
  - 伸びている検索
  - 検索流入があるのに招待CTAが0のページ

## 安全設計

- POIGAME LAB本体の公開HTMLへ埋め込まない
- Apps Script Web AppとしてGoogle側で実行する
- GitHubへOAuthトークン/APIキー/秘密鍵を保存しない
- GA4 / Search Consoleは読み取り専用
- 5分キャッシュでAPI呼び出しを抑える
- GA4かSearch Console片方が失敗しても、もう片方は表示する
- `cta_location` のGA4反映待ちでもダッシュボード全体は止めない

## 初回セットアップ

1. `script.google.com` で新しいApps Scriptプロジェクトを作る。
2. このフォルダの `Code.gs`、`Index.html`、`appsscript.json` を同名で入れる。
3. Apps Scriptのプロジェクト設定でマニフェストを表示し、`appsscript.json` を反映する。
4. エディタで `diagnose` を1回実行し、Googleの読み取り権限を許可する。
5. GA4とSearch Consoleの両方が「接続OK」になることを確認する。
6. 「デプロイ」→「新しいデプロイ」→「ウェブアプリ」で公開する。**第三者公開にはせず、自分だけが使えるアクセス設定にする。**
7. 発行URLをiPhone Safariで開き、「ホーム画面に追加」。名前は例: `POIGAME分析`。

### GA4

POIGAME LAB用GA4 property ID `552686542` を初期値として設定している。
Google Analytics Data APIのApps Script advanced serviceをmanifestで有効化している。

### Search Console

最初に `sc-domain:poigamelab.com` を探す。見つからない場合は、アクセス可能なSearch Consoleプロパティから `poigamelab.com` を含むものを自動選択する。

Search Consoleは読み取り専用REST APIをOAuthで呼ぶ。
もし `accessNotConfigured` / API disabled 系エラーが出た場合だけ、Apps Scriptに紐づくGoogle Cloud projectで **Search Console API** を有効にする。

## データ鮮度

Search ConsoleはGA4よりデータ処理が遅れることがある。
`dataState=all` で取得可能な最新データを含め、画面上部に実際の「Console最新日」を表示する。
GA4とSearch Consoleの日付が完全一致しない場合も、同じ日付として捏造しない。

## 次フェーズ

- 🧪 自分だけ新UIプレビュー
- 🌙 夜勤結果
- ⚠️ GitHub Actions / 自動取得エラー
- 🎮 新ゲーム候補
- 📱 iPhoneショートカットからCOMMAND CENTERを直接開く
- 🤖 ちゃぴ用の安全な分析スナップショット連携
