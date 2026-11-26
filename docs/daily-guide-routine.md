# 日次新規攻略Routine｜運用手順と設定（POIGAME LAB｜毎日新規攻略5本）

毎日、当日の取得データから新規ゲーム攻略を**最大5本**、調査・執筆・実装し、main向け**Draft PR**まで作る運用の正本です。品質を満たさない候補で本数を水増ししません。0〜4本の日はその本数を正直に報告します。

既存の取得処理（`refresh-verified-offers.yml` → `daily_scan_review.py` → `write_new_game_content_queue.py`）は変更せず、出力を入力として再利用します。

## 1. Routine設定値

| 項目 | 値 |
| --- | --- |
| 名前 | POIGAME LAB｜毎日新規攻略5本 |
| 実行 | 毎日 09:00（日本時間）／cron `CRON_TZ=Asia/Tokyo 0 9 * * *` |
| リポジトリ | POIGAME-LAB/poigamelab（既定ブランチ main） |
| モデル | Sonnet 5.5（`claude-sonnet-5-5`） |
| 推論 | High |
| ブランチ | `claude/daily-guides-YYYYMMDD`（Routineの既定どおり `claude/` 接頭辞） |
| コネクター | Notion（CONTROL ROOMの現在地更新）。GitHubはセッションのGitHub連携を使用 |
| 追加費用 | なし（有料API・Tavily・検索API・GitHub Actionsの追加呼び出しなし） |

取得処理の実開始は GitHub の遅延で 05:50〜07:00 JST ごろ（設定 01:17 JST）です。09:00 の時点で `checkedAt` が当日でなければ制作しません（下記 2-2）。

## 2. Routineに貼るプロンプト（全文）

```text
あなたはPOIGAME LABの編集長・ポイ活ゲーム調査員・SEOライター・Webエンジニアです。毎回新しいセッションなので、前日の会話記憶に頼らず、GitHub・当日データ・Notion・未マージPRから状態を復元してください。

## 0. 最初に読む
- AGENTS.md、CLAUDE.md、docs/daily-guide-routine.md、research/daily-guides/README.md を読み、すべて守る（AGENTS.mdが最優先）。
- Notion CONTROL ROOM（https://app.notion.com/p/3e8664b9cf2781ba852fd4f2bd1425d4）先頭の「📍 現在地｜AI共通ステータス」を読む。Notionが使えなければ最後に「Notion未更新」と報告する。

## 1. 状態の復元（書き込み前）
1. 日本時間の今日の日付 D（YYYY-MM-DD）を `TZ=Asia/Tokyo date +%F` で確定する。
2. `git fetch origin` → `git checkout main && git pull origin main`。
3. 既に `origin/claude/daily-guides-<Dの8桁>` ブランチ、または同名のPRがあれば、今日の制作は実施済み。新規制作はせず、そのPRの状態だけ報告して終了する（同じ日に二重制作しない）。
4. GitHubのopen PRをすべて一覧し、各PRの変更ファイルから追加された *-guide.html と research/ 内のゲーム名を集める。
5. `python scripts/daily_guide_candidates.py --scan-remote --exclude "<open PRのゲーム名>" ...` を実行する。
   - 終了コード2（status=stale_input）なら当日データが未取得。GitHub Actions「refresh-verified-offers」の当日runの状況を確認し、前日以前の案件額を使わずに「当日データ未取得のため未制作」とNotionと最終報告に記録して終了する。手動でActionsを起動しない。
   - 「攻略済み」として除外されるのは**攻略記事（公開ページ・実在ページへの登録・同日制作・他ブランチ／open PRの攻略）**だけ。games.csvの比較カタログや過去の調査資料（dossier）があるだけでは除外されず、候補の `relatedMaterial` に「再利用できる資料」として付く（資料がある＝攻略がある、ではない）。
6. `python scripts/daily_guide_triage.py --date D --probe` を実行する（段階A：全候補を無料の事前判定／段階B：公式案件ページを上限つきで確認）。結果は research/daily-guides/D/triage.json。

## 2. 候補の選定
- 順序は triage.json の `rank`（案件を公式ページで確認できる見込み・複数サイト・新着・再利用できる資料などの合成点。報酬は一要素に過ぎない）。報酬ヒントは一覧表示の文字列から読んだ値で、検証済み報酬ではない。scoreは調査の順序であって、記事化できるという判定ではない。
- 段階Aは**全候補**が対象。段階Bの公式ページ確認は `--probe-limit`（既定30・最大40）まで、「見込みのある」検証済み案件（保留済みでなく、公式ページの口コミ件数が0件と分かっていないもの）が `--target-verified`（既定12）見つかった時点で止まる（口コミ0件のゲームも検証済みとして残り、除外はしない）。前日までに保留したゲームは、新しいゲームを調べたあとの余り枠でだけ調べる。1回の実行でのリクエスト数は上限140、アメフリ名前検索は最大20回。この枠を超えて調べない。
- verdict：`offer_verified`（公式ページで条件・報酬・期限を読めた）／`offer_unreadable`（読めなかった。状態は `unreadableReasons` に残る。「終了」「0pt」と解釈しない）／`non_game_or_service`（タイトルにサービス語がある）。ゲーム語もサービス語もない名前は `unclassified`（`gameStatus: unconfirmed`）として、見込みのあるゲームを調べたあとの余りだけで調べる。`offer_verified` でも記事化可能とは限らない。`unclassified` は、ストアでゲームだと確認できるまで記事化しない。
- 深掘り（実プレイヤー調査・ストア同定・攻略情報）は `offer_verified` のゲームを rank順に行い、**独立2人以上・実例3件以上・5年以内（1年超は条件が今と同じものだけ）**を満たす見込みがなければ保留して次へ進む。完成が5本に届くか、`offer_verified` を使い切るまで続ける（上位5件で止めない）。基準は緩めない。
- 同じゲームが複数サイトにある場合、サイトごとに別の案件（金額・条件・期限・ポイント換算が違う）として記録し、1つの表に混ぜない。アメフリの名前検索で見つかった候補は、**名前が一致しても同一アプリと断定しない**（ストアの開発元・アプリIDで同定。似た名前は別アプリの場合がある。例：Onet Master: Puzzle & Art と Onet Master: Tile Match Puzzle）。
- previouslyHeld の候補は、保留理由を解消する新しい根拠がある場合だけ採用する。2026-11-26 の5年ルール変更は、「記録が365日超」だけで保留したゲーム（例：サバイバルアイランド、実りの地、ベガス クレイズ カジノ、キャッシュクラブ）の保留を解消し得る新しい根拠として扱ってよい。その場合も、古い記録の条件が今日の案件条件と同じことをゲートで確認できたものだけ使う。
- 同一ゲームの表記揺れ・OS違い・別案件IDは1本にまとめる。似た名前を同一と断定しない（ストアの開発元・アプリIDで同定）。aliases.json への追加は同定できたものだけ。
- 単体ゲームでないもの（Freecash等の案件集合サービス、動画・配信・金融・公営競技・マッチング等）は除外。

## 3. 採用基準（すべて満たすものだけ完成記事）
案件：実在するゲーム、ポイントサイトの案件ページを当日直接取得。ワラウは `python scripts/daily_guide_evidence.py --date D --slug <slug> <point_id>... --reviews 6`、ワラウ・アメフリ・COINCOME・モッピーの任意の案件ページは `--url <案件URL>`（複数指定可）で記録する（登録済みの公式ホスト以外・http・ログイン情報つきURLは拒否される）。
- **案件の形は2種類**：`stepup`（全Stepの条件・報酬・期限・課金Stepの区別・合計一致）と `single`（単一達成条件：「レベル○○到達」「ステージ○○クリア」等。条件1つ・報酬1つ・期限）。`metadata.json` の offers[].kind に書き、案件ページの記録（evidence）の kind と一致させる。singleに「全Step」の表や文言を流用しない。表は「条件｜期限｜報酬」の1行でよい。
- **読める案件だけが根拠になる**：evidenceの state が `readable` のものだけ。`steps_not_public`（モッピーのStepUpは各成果地点が「POINT GET」後のページにあり公開ページでは合計のみ）・`not_viewable`（ワラウSKYFLAG／SmaAD等の「こちらのページは表示できません」）・`ended`・`not_found`・`http_error`・`parse_failed`・`identity_mismatch` は保留。取得失敗・閲覧不可を「案件終了」「0pt」と扱わない。
- **報酬の単位を混ぜない**：ワラウ 1pt＝1円／モッピー 1P＝1円／アメフリ **10pt＝1円**（ページに「10pt＝1円」の表示があることが条件）／COINCOMEは円表示。evidenceに pointUnit・yenPerPoint が入り、記事の金額はそのサイトの単位で書く（例：モッピー「700P」、COINCOME「340円」、アメフリ「137,790pt（13,779円）」）。アメフリは換算率「10ptが1円」と円換算の合計も本文に書く。サイトによって同じゲームでも金額が違うため、サイトごとの表にする。
- **対象OS**：ページが明記したものだけ。モッピーの単一条件ページにはOSの記載がないことがあり、その場合 os は null のまま、本文に「ページにOSの記載はありません」と書く（推測しない）。
- **増額**：アメフリ「Ptアップ」・COINCOMEのセール表示などは `temporaryIncrease` に記録される。終了日がページにあればその日付を、なければ本文に「増額中」「増額の終了日はページに記載がありません」を書く（期間限定の増額を通常額として書かない）。ワラウも同じ扱い：「1,700pt → 最大2,000pt」のように期限日なしで表示される増額もあり（2026-11-20のプリケツにゃー）、その場合は `until: null`・`endDateStated: false` で記録され、本文に通常額・現在額・「終了日の記載なし」を書く。metadataの `offers[].temporaryIncrease` は証拠と同じ内容にする（食い違いはゲートが拒否）。
攻略：公式ストア（App Store／Google Play）で開発元・アプリIDを確認し、実際の進行システム（資源・施設・レベル・ステージ・イベント）を出典つきで説明でき、序盤・中盤・終盤の具体的な行動を書ける。
実プレイヤー：直近5年以内、独立した2人以上（この基準は案件の形・サイトが増えても緩めない。ゲートが検査する）（同一人物の複数投稿は1人）。実例パネルは3件以上。到達日数・到達地点・課金状況・撤退理由を出典と照合。日数不明はnull（0にしない）。古い仕様の記録はその旨を明記。**1年より前〜5年以内の記録（2026-11-26 運営者決定）**：その人が達成した条件が、今日の案件条件と同じ場合だけ使える。experiences.json の該当プレイヤーに `recordCondition`（記録の中で本人が達成した条件。出典の書き方どおり）と `conditionUnchanged: true` を入れる。ゲートは recordCondition が当日の案件ページの条件文に含まれるかを確認し、違えばその記録を数えない（例：当時は「レベル20」、今は「レベル25」なら使えない）。条件が書かれていない古い記録は使えない。記事の記録パネルには「◯年◯月の記録で、条件は現在と同じ」と自動で表示される。足りなければ保留し、架空の体験談を作らない。当サイトがプレイしたとは書かない。

## 4. 執筆と実装（1本ずつ）
- 1日の完成記事は**最大5本**。根拠不足の候補で5本に水増ししない（0〜4本ならその本数を報告）。`build_daily_guides.py` は6本以上を拒否する。
- research/daily-guides/D/<slug>/ に article.md・metadata.json・sources.json・experiences.json・page.json を作る。形式は research/daily-guides/2026-11-05/mystery-town/ を手本にし、内容はゲームごとに作り直す（言い換えの量産禁止）。
- article.md：H1＝SEOタイトル、導入2段落、目次、節ID condition / pace / outlook / early / middle / late / stop / tracking / faq / sources（pace＝実際の到達ペースの比較表）。各段落の末尾に出典ID［M1］等。編集部の計算・判断は［編集部計算］［編集部判断］と明示し、出典の事実・投稿者の自己申告と区別する。最大報酬を無課金の見込みや利益として書かない。期間限定増額は期限日を明記。
- 画像は使わない（未確認の公式画像・ロゴを転載しない）。関連攻略は実在する公開ページだけ。data/published_offers.csv・取得処理・広告設定・Actionsは変更しない。
- **ゲーム一覧と毎日の金額確認への登録（2026-11-24 運営者決定）**：games.csv に無いゲームの攻略を作ったら、`config/guide_catalog.json` にそのゲームの1件を追加する（game＝攻略一覧の名前、guide、addedDate＝実行日、aliases、condition・days・difficulty・overview・tips）。文言は記事の内容だけを根拠にし、記事に無い数字は書かない。画像は空のまま（サイトの代替表示を使う）。追加後に `python scripts/sync_guide_games.py` を実行すると、games.csv・config/refresh_policy.json・config/game_targets.json・docs/game-images/game-image-manifest.csv に反映される（案件URLは記事内のポイントサイト公式リンクから自動で入る）。`python scripts/sync_guide_games.py --check` が ok になること（CIでも検査する）。games.csv の既存行は変更しない。
- `python scripts/build_daily_guides.py --check research/daily-guides/D` が全件 ok になるまで原稿を直す。テストを通すために事実を変えない・チェックを緩めない。
- `python scripts/build_daily_guides.py research/daily-guides/D` でHTML生成・攻略一覧・sitemap・公開ビルド許可へ登録。攻略一覧の説明文は登録時に一度だけ書かれ、再ビルドでは更新されない。原稿（page.jsonのregistry）を直したら `site-researched-guides.js` も同じ文に直し、`node scripts/sync_static_guide_links.js` を実行する（食い違いはテストが検知する）。口コミの日数は「どのレベル・Stepの話か」が書かれている場合だけ到達日数として使い、書かれていなければ「Stepの記載なし」と明記する。「1週間ちょっと」「2〜3日」「30日前後」のように投稿者が幅を持たせて書いた日数は、実例データの `day` に入れず `null` にして、ラベルに原文の言い回しを残す（2026-11-20以降のバッチはゲートが拒否）。口コミの総数と実例に採用した人数は分けて書く。
- research/daily-guides/D/selection.json（全候補の採用・保留・除外と理由）と REPORT.md（下記10項目）を書く。

## 5. 検証
- pytestが無ければ `python -m pip install -q pytest`（Playwright・Chromiumは環境に導入済み。再インストールしない）。
- `python -m pytest -q tests/test_daily_guides.py tests/test_work_guides_20261031.py tests/test_static_internal_links.py tests/test_generated_guide_registry.py tests/test_new_guides_quality.py tests/test_adsense_quality_static.py`
- `node scripts/sync_static_guide_links.js --check`
- 全体の `python -m pytest -q` は main と比べ、新規失敗が0件であることを確認する（mainの既存失敗は約62件）。全体テストは data/ や research/new-games/ を書き換える副作用があるため、実行後に `git status` を見て、自分の変更以外は `git checkout -- <file>` で戻す。
- Playwright（PC 1280px／iPhone 13／360px）で新ページの横スクロール0、目次リンク解決、実例パネル表示、攻略一覧に1件を確認する。
- 出典URLはすべて当日 HTTP 200 を確認する。

## 6. GitHub
- 完成記事が1本以上あるときだけ、`claude/daily-guides-<Dの8桁>` ブランチを main から作成してコミットし、`git push -u origin <branch>`。
- main向けDraft PRを1つ作成（タイトル例「Daily guides 2026-11-05: N本（ゲーム名…）」）。本文にREPORT.mdの要点・テスト結果・未確認事項を書く。
- 0本の日はPRを作らず、selection.json と REPORT.md はコミットしない（Notionと最終報告に記録）。
- 禁止：mainへの直接push、PRのマージ・自動マージ設定、Draft解除、本番公開、既存PRの変更、取得処理・Actions・広告/アフィリエイト設定の変更、有料サービス・追加課金、ネットワーク制限の解除。アクセスが拒否されたら、実際のエラーと必要な許可範囲を報告する。

## 7. 報告（REPORT.md・Notion・最終メッセージ）
1. 実行日（JST）と使用した取得データの checkedAt  2. 調査したゲーム数  3. 完成記事数  4. 各記事のタイトルとゲーム名  5. 出典の確認状況  6. 保留・除外した候補と理由  7. Draft PRのURL  8. テスト・CI結果（GitHubのcheck runsを確認）  9. 未確認事項  10. 次回への注意点
- Notion CONTROL ROOM先頭の現在地欄だけを更新（日時JST・担当AI・最新PR/コミット・完了/未完了・次の1手・承認待ち・本番/公開データ変更有無・確認根拠）。直前の現在地は日付つき履歴として残す。保存後に再取得して確認する。秘密情報は書かない。これは公開許可ではない。
```

登録済みのRoutineに貼っているプロンプトは、この2章の要点版（順序・禁止事項は同じ）です。Routineは手順0でこの文書を読んで従うため、食い違いがあればこの文書（1章・2章・3章）が正です。

**Routineが動くための前提**（2026-11-14の手動実行で、どれも欠けていると何も作らず安全に停止することを確認済み）：
- このPR（#348）がmainに入っていること（スクリプトと本手順書がmainにあること）。
- Routineの実行環境にPOIGAME-LAB/poigamelabが添付され、push権限があること（無ければブランチもDraft PRも作れない）。
- Notion接続があること（無ければCONTROL ROOMを更新できず「Notion未更新」と報告する）。

## 3. 選定・品質ゲートの実装

| 工程 | 実装 | 守ること |
| --- | --- | --- |
| 当日候補 | `scripts/daily_guide_candidates.py` | 両入力の checkedAt が当日JSTでなければ停止。1pt＝1円のサイトのみ報酬ヒント。**攻略記事（公開ページ・存在するページへの登録・同日制作・他ブランチ／open PR）だけを「攻略済み」として除外**。games.csv・調査資料は除外理由にせず `relatedMaterial` に付与。案件の形のヒント（stepup/single/service）とサイト別URLを付与。案件集合サービスを除外 |
| 事前判定・調査枠 | `scripts/daily_guide_triage.py` | 段階A：全候補を無料判定しサイト×案件の形で「公式ページで確認できる見込み」を点数化。段階B（`--probe`）：上限つき（30〜40ゲーム・140リクエスト）で公式ページを確認、読めなければアメフリ名前検索（名前が同一のものだけ） |
| 案件ページ解析 | `scripts/guide_offer_sources.py` | ワラウ・アメフリ・COINCOME・モッピーの1ページ→共通の証拠形式。state・kind・単位・換算率・増額・期限を明示。HTTPステータスだけで終了と判断しない（COINCOMEは掲載中でも404で届く） |
| 当日の案件証拠 | `scripts/daily_guide_evidence.py` | 1案件1GET。SHA-256・全Step（単一条件は条件1つ）・合計一致・増額期限・対象外条件。口コミ本文は保存しない。`--url` で他サイトも記録 |
| 原稿→公開HTML | `scripts/build_daily_guides.py` | 既存 `render_cited_guide.py`・`register_guide_pages.py`・`sync_static_guide_links.js` を再利用。本文は原稿のまま |
| 品質ゲート | `build_daily_guides.py --check` | 当日証拠と全Step（単一条件は条件）一致、案件の形・OS・単位・換算率・期限の一致、課金Stepの明示、増額の開示、SEO／canonical、目次、出典の当日確認、5年以内（1年超は条件一致のみ）の独立2人以上・実例3件以上、day=0禁止、約束表現の禁止 |
| 回帰テスト | `tests/test_daily_guides.py` ほか | 全バッチの再現性・登録・重複なし＋改ざん検出の否定テスト。`test_guide_offer_sources.py`（実ページ見本で各サイトの状態・単位）、`test_daily_guide_offer_gate.py`／`test_daily_guide_pipeline_kinds.py`（単一条件・アメフリ・COINCOME・モッピーの正常系・異常系）、`test_daily_guide_triage.py`（事前判定・調査枠） |
| 公開前の再確認 | `daily_guide_evidence.py --recheck` | マージ前に案件を取り直す。旧IDは `metadata.previousOffers` に記録し、現行案件として表示しない |
| CI | `.github/workflows/validate-daily-guides.yml` | 既存ワークフローとは別。PRで日次ゲート・静的ハブ同期・日次テスト（上記の新テストを含む）を実行（ネットワーク・Secrets不使用） |

## 4. 既知の限界

- モッピーのStepUp案件は、公開ページに合計額しかなく内訳は遷移先にしかありません（`steps_not_public`）。他サイトで同じゲームの全Stepを確認できない限り保留になります。**モッピーの単一達成条件の案件は、条件・報酬・期限が公開ページに載っているため対象です**（2026-11-19まではStepUp専用の仕組みだったため、これらが全て保留になっていました）。
- ワラウの一部案件（SKYFLAG・SmaAD経由など）は公開ページが「表示できません」になり、確認できません。同じゲームがアメフリ・COINCOMEの公開ページで読める場合は、そちらを根拠にします。
- 日次の `new_game_monitor.json` にはアメフリ案件がほとんど入りません（2026-11-19は256件中1件。広いキューの `new_game_candidate_queue.json` は9月10日のまま更新されません）。アメフリの案件は、triageのアメフリ名前検索（ゲーム名1回につき1GET、最大20回）で補います。候補一覧にない新作ゲームがアメフリだけにある場合は拾えません。
- 実プレイヤー（独立2人以上）の記録は、候補段階では確認できません（ワラウの口コミ件数だけがtriageで分かる）。`offer_verified` のゲームでも、実プレイヤー不足で記事にできない日があります。それでも基準は緩めません。
- `new_game_monitor.json` は表示上限（新着100・継続200）があり、当日スキャンの全件（R2の daily_scan_review.json）はRoutineから読めません。候補はこの公開範囲から選びます。
- iPhone Safari実機、ログイン後の個別条件、実際のポイント付与は確認できません。報告で未確認と明記します。

## 5. 登録済みRoutineへの反映（二重登録しない）

登録済みのRoutine（名前「POIGAME LAB｜毎日新規攻略5本」、trigger id `trig_01WhoixeuBDjiRf6P8jhgQyc`、毎日 09:00 JST）は**新しく作らず、既存の1件のプロンプトだけを更新**します。登録プロンプトは2章の要点版で、手順0で本文書を読んで従う設計（食い違いは本文書が正）ですが、次の記述は本文書の旧版と同じで**新手順と矛盾する**ため、差し替えが必要です。

| 登録プロンプトの記述 | 差し替え |
| --- | --- |
| 「1. 状態の復元」の5の後 | 6を追加：`python scripts/daily_guide_triage.py --date D --probe` を実行（全候補の事前判定＋公式ページの上限つき確認。結果は research/daily-guides/D/triage.json） |
| 「2. 候補の選定」の「candidates.json の順に確認」「（深掘りは最大15候補が目安）」 | 「triage.json の rank 順に確認。公式ページの確認は `--probe-limit`（既定30・最大40）まで、`offer_verified` を実プレイヤー・ストア・攻略情報の深掘り対象にして、基準（独立2人以上・実例3件以上・5年以内、1年超は条件一致のみ）を満たさなければ保留して次へ。上位5件・15件で止めない」 |
| 「3. 採用基準」の案件の項 | 本文書の3章の案件の項（ワラウ以外は `--url`、`stepup`／`single`、読める案件だけ、単位・換算率・OS・増額の扱い） |
| 重複除外 | 「攻略記事（公開ページ・他ブランチ／open PR）だけが攻略済み。games.csv・調査資料は除外理由にしない」 |
| 「5. 検証」のpytest | 末尾に `tests/test_guide_offer_sources.py tests/test_daily_guide_offer_gate.py tests/test_daily_guide_pipeline_kinds.py tests/test_daily_guide_triage.py` を追加 |

**順序**：①このPRがmainにマージされる（スクリプトと本文書がmainにある）→ ②Routineのプロンプトを更新 → ③次の09:00の実行結果（triage.json・REPORT.md）を確認。②を先にすると、Routineが存在しないスクリプトを呼んで停止します（安全に止まるだけで記事は作られません）。

**ネットワーク**：`daily_guide_triage.py --probe` は `pc.moppy.jp`・`www.amefri.net`・`cimcome.jp`・`www.warau.jp` に公開ページを1回ずつ取得します。Routineの実行環境がこれらのドメインを許可していない場合、probesの state が `http_error`（`http_0` / `http_403`）になります。**ネットワーク設定を変えようとせず**、拒否されたドメインとエラーをREPORT.mdと最終報告に書いてください（許可の追加は運営者の判断）。2026-11-19の実行でワラウ・App Store・ブログに届いたことは記録にありますが、アメフリ・COINCOMEへ届くかは未確認です。
