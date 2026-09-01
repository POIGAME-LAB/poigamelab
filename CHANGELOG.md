## V42 — Serialized production writers

- GitHub Actions workflows that can push repository data now share one concurrency group.
- Trend discovery/research and verified-offer refresh can no longer commit generated JSON/CSV at the same time.
- This prevents the rebase conflicts observed when both workflows advanced `main` with overlapping generated data.
- `cancel-in-progress: false` preserves queued work instead of discarding it.

## V41 — Mobile-aware direct research retrieval

- `mobile: true` sources now use a smartphone Safari identity for direct first-party HTTP retrieval.
- This targets device-gated app-offer listings without adding login/session state or weakening first-party/detail-page verification.
- Direct diagnostics now record `deviceMode` (`mobile` / `desktop`).
- Added regression coverage for Moppy `site_id` discovery from a mobile-rendered listing and cross-game rejection.

# PHASE2_DATA_HEALTH_V25

- 自動更新の成功・一部取得・失敗・古さをサイト表示に反映。
- `data/refresh_status.json` と `config/refresh_policy.json` をブラウザ側で安全に読み取り、ゲーム別データ状態を判定。
- 取得失敗/部分取得時は「直前の検証済みデータを保持中」と明示し、古い値を最新値のように見せない。
- データ状況ページを旧候補CSV中心の表示から、検証済み案件・自動更新・例外キュー中心へ更新。
- 48時間を超えた自動更新結果は stale として注意表示。
- V25専用の鮮度/異常系JSテストを追加。

# CHANGELOG

## PHASE2 Site Bridge V24
- `data/published_offers.csv` をトップ/詳細ページの最優先データソースへ接続
- 検証済みゲームでは旧 `offers.csv` を混在させない merge policy を実装
- 自動収集OFFゲームのみ旧データを「参考」としてフォールバック
- 共通 `site-data.js` を追加し、quoted CSV / embedded comma / CRLF を安全に解析
- 自動検証済みバッジと最終更新日をUIへ表示
- 外部由来文字列をHTMLエスケープし、案件URLを http/https のみに制限
- V24フロントエンドテスト追加（CSV、merge、fallback、URL/HTML safety）

## PHASE2 Auto Refresh V23
- 日次GitHub Actions自動更新を追加
- `scripts/auto_refresh.py` を追加
- Township / きのこ伝説のみ自動更新ON
- 完全取得時のみゲーム単位スナップショット置換
- 劣化取得時は前回掲載を保持して成功分だけマージ
- collectionComplete / degradedReasons をCollector出力へ追加
- Publisher出力をatomic replace
- `collect_games.py` が子Collector失敗を正しく終了コードへ反映
- GitHub Actions concurrencyで重複実行を禁止
- 旧6時間候補Collector workflowを停止・historyへ退避

## PHASE3_TREND_DISCOVERY_V26
- 話題/新着ゲーム候補を自動発見する `scripts/discover_trending_games.py` を追加。
- X + 登録ポイントサイト検索を候補ソース化し、Gemini抽出後にPythonで正規化・重複排除・複数ソーススコアリング。
- 候補は `data/trend_candidates.json` / `data/trend_status.json` のみに保存し、ゲーム/案件の公開データは変更しない安全境界を固定。
- GitHub Actions `Discover trending games` を毎日07:07頃(JST)に追加。既存Secretsを再利用。


## V27 — PHASE3 research promotion
- Added deterministic, API-free trend candidate promotion into `data/research_queue.json`.
- Requires independent-source, confidence, score, and point-site-evidence gates.
- Known games/aliases are blocked from promotion; publication and game target files remain untouched.
- Trend workflow now commits the research queue alongside candidate-only outputs.

## V28 — PHASE3 quarantined collector bridge
- Promoted research candidates can now enter the existing strict offer collector/verifier without being added to `game_targets.json`.
- Research runs force `POIGAMELAB_PUBLISH_MODE=quarantine`; verified offers are saved under `data/research_results/` and never written to public offer data.
- Daily trend workflow researches at most one promoted game per run to cap API cost.
- Unicode-only game names now receive collision-resistant hashed result slugs.

## V29 — PHASE3 final adoption gate
- Added API-free `scripts/evaluate_research_adoption.py` to judge quarantined research before any public-data mutation.
- Adoption readiness requires a complete, non-degraded collection plus at least 2 strict verified offers from at least 2 registered point-site sources.
- Every accepted offer must retain the V20 exact same-offer identity/reward consistency checks; weaker legacy-style verification cannot pass.
- Output is candidate-only `data/adoption_candidates.json`; V29 never edits `games.csv`, `game_targets.json`, `offers.csv`, or `published_offers.csv`.
- Research queue now fingerprints evidence and preserves completed/failed state when evidence is unchanged, preventing repeated daily API research of the same candidate.

## V30 — PHASE 3 Production Adoption
- V29 `adoption_ready` games can now be promoted into `games.csv`, `config/game_targets.json`, and strict verified offers into `data/published_offers.csv`.
- Production adoption is API-free and re-runs the V29 deterministic gate immediately before writes.
- New games enter `refresh_policy.json` with scheduled refresh disabled, preventing an unknown-game API crawl from silently becoming a recurring cost.
- Adoption is idempotent; game/offer duplicates are not created on reruns.
- Workflow records `data/adoption_status.json` and commits production changes only after the final gate.

## V31 — PHASE 3 Integration Safety Audit
- Added an API-free, fail-closed audit after production adoption and before Git commit.
- Blocks commits on duplicate games/targets/offer keys, orphan published games, invalid URLs, incomplete adoption registry state, enabled refresh for newly adopted games, or offer-count mismatch.
- Made `data/research_results/` staging conditional so a no-research run cannot fail on a missing directory.
- Added integration/negative-path tests; no live API calls are used by the audit.

## V32 — Discovery Evidence Recovery
- Point-site search failure/zero-result now falls back to stable first-party listing pages for Warau and COINCOME.
- Fallback runs only when needed, avoiding duplicate Firecrawl spend on healthy searches.
- Diagnostics distinguish search failure from fallback recovery/failure.
- Research thresholds are unchanged; V32 improves evidence collection instead of weakening the gate.

## V33 — Discovery failure diagnostics
- `data/trend_status.json` now retains per-source discovery diagnostics instead of only the aggregate `failedSources` count.
- Records search result count, whether fallback was attempted, fallback result count, and bounded error summaries for each source.
- Error text is flattened, length-limited, and redacts authorization/API-key/token-like values before persistence.
- Discovery, scoring, promotion thresholds, and API call behavior are unchanged; V33 is diagnostic-only.

## V34 — Direct-first discovery resilience
- Added allowlisted direct HTTP retrieval for stable first-party Warau and COINCOME listing pages.
- Firecrawl is now best-effort fallback for discovery instead of a single point of failure.
- Discovery can continue when Firecrawl is out of credits; strict promotion/adoption gates are unchanged.
- Diagnostics now distinguish direct HTTP attempts from Firecrawl attempts.

## V35 — Free-source coverage + deterministic discovery confidence
- Added the official Moppy poikatsu game editorial page as a third direct, no-Firecrawl point-site discovery source.
- Discovery confidence is now derived deterministically from independent evidence sources; Gemini confidence is retained only as diagnostic `modelConfidence`.
- A single source cannot pass the existing 2-source research gate even if Gemini reports high confidence.
- Existing V27 research thresholds are unchanged.

## V36 — Direct discovery coverage + conservative game identity
- Expanded Warau direct discovery with a second stable first-party service listing that currently exposes established game offers missed by the narrow new-game page.
- Direct listing URLs now retain only allowlisted public selector query parameters, preventing distinct configured listing pages from collapsing during pre-Gemini deduplication while dropping tracking/session-like parameters.
- Added deterministic conservative game identity normalization for platform/provider decorations and trailing StepUp markers only.
- Split Gemini rows such as `ロイヤルマッチ（StepUp）` and `ロイヤルマッチ` can now merge only when their deterministic identity matches; V27 score/confidence/source-count thresholds remain unchanged.

## V37 - Long listing extraction coverage
- Replaced silent 5,000-character extraction truncation with bounded long-page chunking.
- Preserves source/url identity across chunks, so repeated chunks from one page never count as independent sources.
- Batches Gemini extraction with hard caps on chunk count and batch count to bound API cost.
- Keeps V27 research thresholds unchanged and preserves Firecrawl 402 degraded-mode behavior.

## V38 — Direct-first research collector resilience
- Added bounded allowlisted first-party HTTP retrieval to the quarantined offer research collector before any Firecrawl call.
- Stable official listing pages are used only to discover target-adjacent first-party detail links; a detail page must independently contain the target before it can become verifier evidence.
- A successful direct detail path skips Firecrawl for that source, so Firecrawl 402 cannot erase already-collected first-party evidence.
- Firecrawl remains best-effort fallback for sources where direct retrieval cannot establish a detail page; degraded sources remain visible to V29 and cannot be silently adopted.
- `FIRECRAWL_API_KEY` is no longer a hard prerequisite for research when direct first-party evidence is available; Gemini remains required for structured extraction.
- Existing V20 exact-offer identity/reward gates, V29 two-source adoption gate, quarantine boundary, and Firecrawl concurrency cap are unchanged.

## V39 — Card-context official detail discovery
- Direct research no longer requires the target game name to be inside the clickable anchor label; image-only and whole-card links can be associated with a sibling game title inside the same bounded offer card.
- Card-context discovery accepts only registered first-party detail-shaped URLs and stops at unrelated branching card/listing boundaries, preventing a page-level target mention from blessing neighbouring game links.
- Every discovered detail page is still fetched and must independently confirm the target before becoming verifier evidence; V20 exact-offer identity and V29 multi-source adoption gates are unchanged.
- Added explicit per-source official detail URL hints for Warau, Moppy, Chobirich, and COINCOME while preserving bounded direct-detail fetch limits and Firecrawl fail-soft fallback.

## V40 — Moppy stable identity + adoption hold diagnostics
- Added Moppy's current public `site_id` selector to the stable offer-identity allowlist used by both research verification and publishing; tracking parameters remain stripped.
- Distinct Moppy iOS/Android detail IDs can no longer collapse to the same path-only identity, preserving the V20 exact same-offer invariant for a future second-source adoption.
- Moppy `site_id` is recognized as a detail-selector shape without hardcoding any current game-specific offer ID or reward.
- V29 adoption logs now print bounded API-free HOLD/READY diagnostics with exact reasons, strict-offer count, and verified source names, so a safe hold can be diagnosed from one workflow run without exposing offer URLs.

## V43 — Versioned research recheck
- Added an explicit research-logic version to the PHASE 3 queue so already-researched promoted games are requeued once when collector capability changes.
- A completed research run records the logic version it used; subsequent unchanged discovery runs stay cached and do not repeatedly spend Gemini/retrieval calls.
- Candidate-evidence changes still trigger research independently, while V27 promotion thresholds, V20 strict verification, V29 adoption thresholds, and quarantine publication boundaries remain unchanged.

## V44 — Indexed official-detail discovery fallback
- Added optional Tavily discovery for registered point sites whose public listing is login/JS gated; search results are URL hints only and never verifier evidence.
- Every discovered URL must be registered first-party, match an official detail shape, be fetched directly, and independently confirm the target game before entering Gemini or the strict verifier.
- Wired `TAVILY_API_KEY` into the trend/research workflow as an optional secret and bumped the research-logic version so held games are rechecked once after this capability change.
- Existing V20 exact-offer identity, V29 two-independent-source adoption gate, quarantine boundary, and Firecrawl fail-soft behavior remain unchanged.

## V45 — clean public discovery completion
- Treat a successful Tavily indexed-official discovery pass with no verified target as a clean technical completion, while explicitly keeping absence non-authoritative.
- Do not invoke failing Firecrawl fallback after a clean public discovery pass; direct-detail verification failures still remain degraded/fail-closed.
- Preserve V20 strict identity and V29 independent-source adoption requirements unchanged.
- Bump research logic version so held games are rechecked once with the corrected completion semantics.

- V46: collection completeness now treats earlier stale known-page misses as superseded only after a clean terminal first-party/indexed discovery state; real terminal failures and partial known fast paths remain fail-closed.

## V47 — Optional Firecrawl coverage isolation
- V29 now distinguishes Firecrawl HTTP 402 billing exhaustion from evidence failure only for quarantined research.
- The exception is fail-closed: every degraded reason must be a matching `search_failed` 402 with completed public-discovery diagnostics, and adoption still requires the configured minimum strict offers and independent verified sources.
- Production refresh `collectionComplete` semantics and snapshot-preservation behavior are unchanged.
- Fatal, partial, non-402, unknown, or insufficient-evidence cases remain HOLD.

## V48 — Moppy indexed query diversity
- Added bounded Moppy-only Tavily query diversity for intermittent indexed-detail misses.
- Common success path remains one Tavily call; up to three exact-target/first-party variants are tried only when earlier variants do not yield a directly verified official detail page.
- Search snippets/titles remain discovery hints only. Every candidate must still be a registered Moppy detail URL and the fetched official page itself must contain the target.
- Deduplicates stable offer identities across query variants and rejects external domains.
- Stale/404 detail results can be bypassed by a later query variant; all-query/partial query failures remain fail-closed.
- Bumped researchLogicVersion to V48 for one controlled recheck.

## V49 — PHASE 4 guide evidence quarantine
- Added a manual-only Phase 4 workflow for guide-source discovery.
- Tavily is discovery-only; every retained page is fetched directly and must confirm the target game in page content.
- Added deterministic URL canonicalization, point-site exclusion, source typing, content hashes, dedupe, and bounded search/fetch calls.
- No generated攻略 text or production site data is modified in V49.

## V50 — Phase 4 evidence-bound guide claims
- Added quarantined Gemini claim extraction after V49 direct evidence collection.
- Python requires each AI claim to cite a known source and an exact quote present in the re-fetched page; unsupported or numerically ungrounded claims are rejected.
- AI usage is bounded to one call per game (up to eight directly re-fetched evidence pages), with fail-closed behavior on fetch/API failures.
- Claim output remains quarantined and cannot write public game/site data.
- Phase 4 workflow now tests both V49 collection and V50 claim contracts and uploads claim artifacts for inspection.

## V51 — Deterministic guide claim support/conflict gate
- Added an API-free gate after V50 that separates evidence-bound claims into supported quarantine, single-source hold, or numeric-conflict hold.
- Community claims need corroboration from at least two independent source sites; duplicate pages and subdomains of the same site do not inflate support.
- Official-source claims may satisfy support alone, but deterministic same-template numeric conflicts override support and hold every conflicting variant.
- Paraphrases are intentionally not fuzzy-merged, avoiding false corroboration from merely similar wording.
- All V51 outputs remain quarantine-only with zero publication eligibility and zero production writes.
