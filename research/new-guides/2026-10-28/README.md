# 新規攻略3本 実装・監査記録（2026-10-28）

公開されないリポジトリ内の記録です（`build_public_site.py` の許可リストに含まれません）。

対象：ザ・グランドマフィア／Bingo Blitz／Heroes vs Crazy Wiggler。ChatGPT Work が 2026-10-27 に制作した原稿
（`POIGAME_LAB_3Guides_2026-10-27.zip`）を、**攻略ページのみ追加**として実装した。`games.csv`・`data/published_offers.csv`・
自動取得・金額更新・AdSense・Cloudflare・既存画像・既存攻略は変更していない。

## ファイル

- `work-originals/` … 納品された原稿 `article.md` / `metadata.json` / `experiences.json` と `sources.json`・`SHA256SUMS.json` の写し（無改変）。
- `tools/md_to_spec.py` … `article.md` を仕様のブロック構造へ変換するだけ（文言は変えない）。
- `tools/build_specs.py` … 監査で決めた修正を `CORRECTIONS` / `INSERTIONS` として明示し、`<slug>.json`（仕様）を生成する。
  修正前の文が1か所に一致しなければビルドが失敗する。`python research/new-guides/2026-10-28/tools/build_specs.py`
- `<slug>.json` … `scripts/render_guide_from_spec.py` の入力。`inlineMarkup: true` で `[G1]` 等の出典IDを出典一覧への
  アンカー、`**太字**`・`[ラベル](URL)` を HTML に変換する（フラグなしの既存10本の出力は不変）。

```sh
python scripts/render_guide_from_spec.py research/new-guides/2026-10-28/*.json
python scripts/register_guide_pages.py   research/new-guides/2026-10-28/*.json
node   scripts/sync_static_guide_links.js
python -m pytest -q tests/test_work_three_guides.py
```

## ZIP の確認

25ファイル。`SHA256SUMS.json` に載る24ファイルのSHA-256は全て一致。

## 原稿から修正した箇所（`build_specs.py` と1対1）

| 記事 | 箇所 | 修正内容 |
| --- | --- | --- |
| グランドマフィア | 条件表の注記 | 「案件の全体期限はインストールから60日以内」を削除。成果到達期限・成果調査受付期限・問い合わせ期限は別々に記載され、起算日と日数の表記が一致しない場合があること、個別Stepの「○日間」の起算日がアメフリiOSには明記されていないことを記載 |
| グランドマフィア | 成果反映の注意点 | 「アメフリの調査受付も60日以内」を削除し、「クリックから60日（成果到達）／クリックから50日（調査受付）」の記載、「インストールから60日」と表示された取得結果もあったこと、51〜60日目の扱いは断定できないことを追記 |
| グランドマフィア | T4（Step11・12） | 30日・60日のT4が同一の到達目標であること、両方の報酬は必ず付与されるとは言えないことを条件表の直後に注意として追記。FAQの文言も「両方の報酬が必ず付与されるとは言えません」へ |
| グランドマフィア | Android別コース | 「別荘9・17、Tier2・3までが7日以内」→「別荘9・17・21とTier2・3が7日以内、期限はすべてインストール日から」「Tier4は30日以内の1条件」（ワラウ案件ページで確認） |
| グランドマフィア | 同定 | App Store掲載（ID 1612013407、Google Playと同じバンドルID）を出典G6として追加。マフィア・シティが別アプリであることをFAQへ追記 |
| Bingo Blitz | 冒頭 | 「現行のキョート・アルプス完走日数」→「現行コースの最終都市（Androidはキョート、iOSはアルプス）までの完走日数」 |
| Bingo Blitz | 21歳以上 | 出典に公式サイトB1を追加（B6のみ→B1・B6）。App Storeの年齢表示は17+（B8）であることを追記 |
| Bingo Blitz | 金額 | 通常表示（Android 21,600pt／iOS 15,200pt）と、増額表示が10月31日までで以降変わる可能性、iOSの最終条件アルプス5,900円相当、広告主表記とApp Store提供元の一致（ストアIDの遷移先は未確認）を追記 |
| Heroes | 同定 | 広告主表記（IMIYOO）とApp Store提供元の一致を追記（遷移先ストアIDは未確認）。ノーマル2・6・10の合計50円相当に出典H2を付与し強調表示 |
| 3記事共通 | 出典ID | 本文中の `[G1]` 等を出典一覧へのアンカーに変換。各記事は自分のID（G/B/H）とR番号だけを参照。他ゲームのIDやURLへはリンクしない |
| 3記事共通 | 実例 | `experiences.json` は納品データをそのまま使用。グランドマフィアの導入文にOS・出所を追記、Dの注記に「当時の案件・OS不明」、Bに「Aと同じ7日でも進行に差」、Heroesの日付不明・幅付き記録に表示ラベルを付与、`updatedAt` を 2026-10-28 に更新 |

`handoff.md`（Bingo Blitz・Heroes）に残っていた「`[G1]`等」の説明は納品物の運営メモで、公開ページには出ていない。
公開ページ側は出典IDと記事の対応をテストで固定した（`tests/test_work_three_guides.py::test_citations_link_only_to_this_games_sources` ほか）。

## 2026-10-28 の再確認結果（Claude の直接取得）

| 項目 | 結果 |
| --- | --- |
| アメフリ137656（iOS） | 12Step・701,980pt＝70,198円相当（10pt＝1円）。個別期限は Step6=7日 / 7=15日 / 8〜11=30日 / 12=60日、Step1〜5は期限記載なし。審査待ちなし・承認通知のみ |
| アメフリ137656 の期限表記 | **取得結果は「成果到達期限：インストールから60日以内」「成果調査受付期限：インストールから60日以内」。ChatGPT監査の「クリックから60日／クリックから50日」とは一致しなかった**。問い合わせ期限は「ポイントを貯める」ボタンのクリック日から60日（非承認理由は成果判定日から30日）。個別Stepの起算日の記載は見当たらない。記事は両方の表記を併記し、最も安全側に計画するよう案内した |
| ワラウ206954（Android） | 最大55,000pt。別荘9・17・21とTier2・3が7日、別荘23が15日、別荘25・監禁所25・投資センター25・Tier4が30日。すべてインストール日から起算 |
| ワラウ207591（Bingo Blitz Android） | 15Step合計27,770pt（通常表示21,600pt、10/31まで増額）、課金2条件（450円＋1,800円）を含み購入除外25,520円。期限5/10/20/40/85日、すべてインストール日から |
| ワラウ207589（Bingo Blitz iOS） | 15Step合計17,770pt（通常15,200pt、10/31まで増額）。アトランティックシティ1日、トーキョー5日、最終はアルプス5,900pt |
| ワラウ205754（Heroes iOS） | 12Step合計11,400pt。ノーマル2・6・10＝6＋14＋30＝50pt。購入条件は赤いダイヤ4990／9990／19990の一括購入（青いダイヤは対象外）計1,220pt、購入除外10,180pt。インストール日から30日 |
| 換算 | ワラウ「原則1pt＝1円」／アメフリ「10pt＝1円」を取得ページで確認 |
| ストア同定 | App Store: ザ・グランドマフィア ID1612013407（Yotta Games Japan Ltd、com.yottagames.gameofmafiajp。Google Playの公式パッケージと一致）、マフィア・シティ ID1235569398（com.yottagames.mafiawar）は別アプリ。Bingo Blitz ID529996768（Playtika Santa Monica、17+）。Heroes ID6758664314（IMIYOO PTE. LTD.、version 200、9+）。広告主表記（ワラウ）との一致は Bingo Blitz・Heroes で確認 |
| 21歳以上（Bingo Blitz） | 公式 bingoblitz.com に「intended for those 21 and older」、Playtika公式ニュースに「for players 21 years of age or older」。ワラウ案件ページに年齢の記載はない |
| 実プレイヤー記録 | ワラウのクチコミ（けいちゃん9/27・とむ10/20・じろう9/13・すーな5/16・Ｏｒｚ8/24）と、note（maf252）、はてな・FC2・アメブロ各ブログの本文を直接取得し、日数・課金額・時間が原稿と一致することを確認 |
| 外部リンク | 記事・実例が参照する20URLは全て HTTP 200（内容は上記のとおり本文で確認済み） |
| 既存記事との重複 | 公開中の攻略（*-guide.html 35本＋township 2本）・games.csv・data/published_offers.csv に3ゲームは存在しない |

## 未確認・保留

- アメフリ137656の期限表記（クリック／インストール、50日／60日）。ページの表記が取得ごとに異なる可能性があり、運営者による実画面の確認が必要。
- 案件ボタンから先の実際のストアID（広告リンクの遷移は操作していない）。
- T4（グランドマフィア）の両Step付与の実運用、Bingo Blitz現行最終都市・Heroesヘル70の完走実例、赤いダイヤの現在価格、Bingo BlitzのPLUS条件。
- Bingo Blitzの増額表示は **2026年10月31日まで**。公開が11月以降になる場合は、金額（27,770／17,770）を再取得して更新するか注記を見直すこと。
- ワラウ「判定中」記帳・購入証明など実際の付与は実機で確認していない。
