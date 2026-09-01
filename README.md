# POIGAME LAB — PHASE 2 Data Health V25

V23でGitHub Actionsの日次自動更新が本番稼働したため、V24ではその**検証済みデータを実サイトへ直結**しました。



### V41 mobile-aware direct retrieval

Research direct HTTP honors each source registry entry's `mobile` flag. Mobile app-offer sources are fetched with a smartphone Safari user-agent, while the same registered-domain, detail-shape, target-confirmation, and exact-offer identity gates remain unchanged. No login/session state is introduced.

## V24: サイト表示への接続
- トップ/詳細ページは `data/published_offers.csv` を最優先で読む
- 自動検証済みデータがあるゲームは、旧 `offers.csv` の未確認値を混ぜない
- まだ自動収集OFFのゲームだけ `offers.csv` を参考データとしてフォールバック
- 「✓ 自動検証済み / 更新日」と「△ 参考データ」を表示で区別
- CSVの引用符・カンマを正しく扱う共通パーサー `site-data.js` を追加
- スクレイピング由来テキストのHTMLエスケープ、リンクの http/https 制限を追加

## 自動更新フロー
GitHub Actions → `scripts/auto_refresh.py` → ゲーム別Collector →
Python deterministic verifier → Publisher → `data/published_offers.csv`

対象は現在:
- Township
- きのこ伝説

メメントモリ / ワーキングヒーローは、公式案件URLの精度検証前なので自動更新OFFです。

## データ保護
- 完全取得: そのゲームの掲載スナップショットを最新状態へ置換
- 429/取得失敗などの劣化取得: 成功した新データだけマージし、前回の正しい行を消さない
- CSV/JSONは一時ファイルからatomic replace
- exact offer identity / reward consistency gateは維持
- Firecrawl同時通信は全体最大2
- GitHub Actions自体も同時実行1本

## GitHub Actions
`.github/workflows/refresh-verified-offers.yml`
- 手動実行可能
- 毎日 21:17 UTC（日本時間 06:17頃）
- Repository Secretsとして `FIRECRAWL_API_KEY` と `GEMINI_API_KEY` が必要
- APIキーをコードやZIPへ保存しない

旧6時間Collector workflowは `docs/history/collect-data.legacy.yml` へ退避済み。

## V25: データ鮮度・異常表示

サイトは `data/refresh_status.json` を参照し、ゲームごとの自動更新状態を `正常 / 一部取得できず / 更新失敗 / 更新待ち` として表示します。部分取得や一時障害では Publisher が以前の検証済み案件を保持し、UI側もその状態を明示します。`config/refresh_policy.json` の `staleAfterHours`（既定48時間）を超えると更新待ち表示になります。

## V26: PHASE 3 話題ゲーム候補の自動発見

`Discover trending games` が毎日07:07頃(JST)に、X検索結果と登録ポイントサイトのゲーム案件検索から新規ゲーム名候補を収集します。Firecrawlは検索結果取得、Geminiはゲーム名候補の抽出だけを担当し、PythonがURL正規化・重複排除・複数ソースのスコアリングを行います。

**安全境界:** V26は候補発見専用です。`games.csv`、`offers.csv`、`data/published_offers.csv` を自動変更しません。出力は `data/trend_candidates.json` と `data/trend_status.json` のみです。既知ゲームは新規候補から区別されます。


## PHASE 3 V27 research promotion
Strong V26 trend candidates are deterministically promoted to `data/research_queue.json` only when score/confidence/source-count thresholds pass and point-site evidence exists. This stage makes zero API calls and never edits publication data or `game_targets.json`.

## PHASE 3 V28 research collector bridge
`collector_ready` candidates can be researched automatically with the existing Firecrawl + Gemini + deterministic verifier pipeline. V28 is deliberately quarantined: it does not add the game to `game_targets.json` and does not update `data/published_offers.csv`. At most one promoted game is researched per daily trend run; results are stored in `data/research_results/` for the next publication-decision stage.

### PHASE 3 V29: final adoption gate
`python scripts/evaluate_research_adoption.py` evaluates quarantined V28 research with zero API calls. A game becomes `adoption_ready` only after complete/non-degraded collection and multiple strict same-identity verified offers across multiple registered point sites. V29 still does not publish or add games automatically. Unchanged already-researched candidates retain their state so the daily trend workflow does not spend API calls researching them again.

### PHASE 3 V30 production adoption
`python scripts/adopt_verified_games.py` consumes only V29 `adoption_ready` decisions. It revalidates the quarantined collector result without API calls, adds the game to the catalog/target registry, and merges only strict verified offers into the canonical published CSV. Newly adopted games are intentionally added to the refresh policy with `enabled: false`; recurring unknown-game crawling is a separate controlled policy decision.

### PHASE 3 V31 safety audit
The trend workflow runs `scripts/audit_phase3_pipeline.py` after V30 adoption and before committing. The audit is API-free and fail-closed: inconsistent production state stops the workflow before Git writes are pushed. `data/research_results/` is staged only when present.

### PHASE 3 V32: discovery evidence recovery
Trend discovery keeps the strict V27 promotion thresholds. When a point-site search fails or returns zero results, V32 may scrape a configured stable first-party listing page once as recovery evidence. Healthy searches do not trigger the fallback, and failed recovery remains visible in diagnostics.

### PHASE 3 V33: discovery failure diagnostics
`data/trend_status.json` now includes a `diagnostics` array for each configured discovery source. It records search/fallback outcomes and safe bounded error summaries, so a `failedSources` count can be traced to the failing stage without changing discovery thresholds or adding API calls. Secret-like authorization/token/API-key text is redacted before status persistence.

### PHASE 3 discovery resilience (V34)
Stable official listing pages are fetched directly first (Warau / COINCOME). Firecrawl remains a fallback for sources that need it. A Firecrawl 402 therefore no longer forces all discovery sources to zero. Candidate promotion and production adoption thresholds remain unchanged.

### V35 discovery safety
PHASE 3 now has a third direct first-party point-site source (Moppy official poikatsu game editorial) that does not consume Firecrawl credits. Candidate `confidence` is evidence-derived in Python; Gemini's self-reported value is diagnostic only (`modelConfidence`). Research promotion still requires the existing score/confidence/independent-source gates.

### V36 discovery coverage and identity
Warau discovery now reads two bounded official first-party listing views instead of relying on one narrow page. Direct-listing selector query parameters are preserved only from a fixed allowlist so those pages remain distinct without retaining tracking data. Candidate identity normalization is deliberately conservative: it removes known platform/provider decorations and a trailing StepUp campaign marker, but does not fuzzy-match arbitrary similar titles. Independent-source promotion thresholds are unchanged.

### V37 discovery extraction safety
Long official listing pages are split into bounded overlapping text chunks before Gemini name extraction instead of silently discarding everything after 5,000 characters. Chunk evidence keeps the original page/source identity, so one page can never become multiple independent sources. Chunk and batch caps bound Gemini calls; Python promotion thresholds remain unchanged.

### V38 direct-first research collector
The quarantined research collector now mirrors the discovery layer's resilience strategy: registered first-party listing pages are fetched directly first, target-adjacent official detail links are followed within the same registered domain, and only detail pages that independently confirm the target become verifier candidates. Firecrawl is fallback-only for that source. A 402 on another source remains a degraded reason, so V29 still fails closed rather than treating missing coverage as complete. Direct listing/detail counts are bounded per source, and the existing exact same-offer verifier is unchanged.

### V39 card-context direct research
Official point-site listings often make an image or the entire card clickable while the game title is rendered in a sibling element. V39 adds a dependency-free bounded HTML card-context matcher for those layouts. It only considers registered first-party URLs with known detail-like shapes, refuses to climb past an unrelated branching card/listing boundary, and then re-fetches the candidate detail page to confirm the target name. This improves direct Warau-style extraction without weakening quarantine, exact-offer verification, source independence, or V29 adoption requirements.

### V40 Moppy identity hardening and adoption diagnostics
Moppy currently uses a public `site_id` query selector on ad detail pages. V40 treats that selector as stable offer identity while continuing to remove tracking/session parameters, so separate platform offers cannot collapse before exact-offer verification or publishing. No current game-specific Moppy ID is embedded in production logic. The V29 adoption step also emits concise HOLD/READY reason lines with strict-offer and independent-source counts; thresholds remain unchanged.


### GitHub Actions writer safety (V42)

Both repository-writing workflows use the shared `poigamelab-production-writer` concurrency group with `cancel-in-progress: false`. This serializes generated-data commits from trend/research and verified-offer refresh jobs and avoids bot-vs-bot rebase conflicts on overlapping `data/` outputs.


### V43 research recheck policy
PHASE 3 records `researchLogicVersion` in `config/trend_discovery.json`. A promoted game already researched under an older collector logic version is queued exactly once for re-research; after completion, `lastResearchLogicVersion` prevents repeated runs until either candidate evidence or the declared research logic changes again.

### V44 indexed official-detail fallback
When a registered point site's public listing is login/JavaScript gated, research may optionally use Tavily to discover indexed official detail URLs. Search snippets are never evidence: the collector directly fetches the registered first-party detail page and re-confirms the target before Gemini/verifier processing. Configure `TAVILY_API_KEY` as a GitHub repository secret to enable this fallback.

### V45 collection completeness semantics
A source can finish cleanly after its public indexed-official discovery strategy completes even when it finds no verified target. This means only that the configured public discovery attempt completed without a technical error; it does **not** prove that the point site has no matching offer. No negative offer evidence is published. Adoption still requires strict verified offers from at least two independent registered sources, and any failure while directly verifying an eligible official detail URL remains degraded/fail-closed.

- V46: collection completeness now treats earlier stale known-page misses as superseded only after a clean terminal first-party/indexed discovery state; real terminal failures and partial known fast paths remain fail-closed.

### PHASE 3 V47 — optional Firecrawl failure isolation
For quarantined trend research only, V29 may treat Firecrawl `402 Payment Required` as an optional retrieval-layer warning after public first-party discovery has produced complete diagnostics. This never asserts that an inaccessible source has no offer, never changes Phase 2 production snapshot completeness, and never bypasses the strict-offer / independent-source thresholds. Any fatal, partial, non-402, unknown, or evidence-insufficient state still fails closed.

### V48 Moppy indexed discovery resilience
Moppy indexed discovery uses at most three sequential Tavily query variants when the first exact-title query misses. It stops immediately after a Moppy official detail page is directly fetched and target-confirmed, keeping the usual API cost to one search. Search snippets are never evidence, external domains are rejected, stable identities are deduplicated, and unsuccessful/partial searches cannot create authoritative absence evidence.

### PHASE 4 V49 — guide evidence quarantine foundation
攻略情報は公開文面を直接生成する前に、独立した隔離パイプラインで根拠URLを収集します。Tavily検索結果はURL発見専用で、検索タイトル/スニペットを攻略事実として採用しません。候補ページを直接取得し、対象ゲーム名をページ本文で再確認したものだけを `data/guide_evidence.json` に保存します。ポイントサイト案件ページは攻略根拠から除外し、追跡パラメータを落として重複排除します。V49は本文・tips・公開CSVを一切更新しない candidate-only / quarantine-only 段階です。GitHub Actions workflow は安全のため `workflow_dispatch` の手動実行のみです。

### Phase 4 V50: evidence-bound claim quarantine
After V49 discovers and directly verifies guide pages, `scripts/extract_guide_claims.py` re-fetches those pages and asks Gemini to propose small guide claims. Gemini is not the publication judge: Python accepts a proposal only when its source ID is known and its quoted evidence is literally present in that source. Numeric claims must ground every number in the quote. Outputs stay in `data/guide_claims.json` / `data/guide_claim_status.json` as quarantine artifacts; no public game or site data is written. AI calls are bounded to one per game and at most eight evidence pages are re-fetched per game.

#### Phase 4 V50.1 extraction diagnostics
V50.1 does not relax claim extraction or publication rules. It adds a safe aggregate diagnostic summary to `data/guide_claim_status.json` and the Actions log so a zero-claim run can be distinguished as: no re-fetched sources, Gemini error, malformed `claims` payload, Gemini proposing zero claims, or all proposed claims being rejected by Python. The summary exposes counts only (including input evidence, re-fetched sources, target-missing pages, proposals, validated claims, and rejection reasons); it does not print source text, quotes, URLs, or secret-bearing error messages.

### PHASE 4 V51 — deterministic guide claim support/conflict gate
`python scripts/evaluate_guide_claims.py` evaluates only V50 `validated_quarantine` claims with zero API calls. Community claims require matching conservative claim identity across at least two independent source sites; multiple pages/subdomains from the same site count once. A configured `official` claim may pass the support gate alone, but exact-template numeric conflicts are held even when one side is official. V51 deliberately does not fuzzy-merge paraphrases, does not generate guide copy, and keeps every decision quarantined with `publicationEligible: false` and `publicationWrites: 0`.

### PHASE 4 V52 — bounded corroboration
V52 researches only V51 `held_single_source` claims. Tavily remains URL discovery only; every candidate is directly fetched, target-confirmed, and must come from an independent source site. Gemini may map a literal quote to an existing held claim, but Python verifies quote presence, exact numeric-token grounding (so `20` is not accepted from `120`), and conservative lexical overlap. Search/fetch/API work is bounded and all outputs remain quarantined with `publicationWrites: 0`. A second V51 evaluation runs against the corroborated claim set.

#### Phase 4 V52.2 re-evaluation guard
The post-corroboration V51 pass is invoked with an explicit `--input data/guide_claims_corroborated.json` plus an expected phase marker. The run fails closed if the wrong quarantine dataset is supplied. V52 reports both input and output claim counts for auditability.

#### Phase 4 V52.3 corroboration diagnostics
V52.3 keeps the V52 support gate unchanged but makes a zero-match run diagnosable from one workflow log. `diagnosticCounts` reports the bounded search/fetch/AI funnel, including stale/orphan held decisions, malformed search/AI payloads, invalid or unsupported URLs, duplicate URLs, same-source-site exclusions, blocked/unsafe URLs, fetch failures, target-missing pages, AI proposal/rejection counts, validated relation counts, and candidate pages that Gemini never referenced. Match validation also re-checks source independence for the specific mapped claim, so cross-claim remapping cannot turn an existing source site into fake corroboration. Contradiction evidence must share conservative lexical context with the held claim. All results remain quarantine-only with `publicationWrites: 0`.

#### Phase 4 V52.4 evidence-span grounding
Corroboration no longer asks Gemini to copy an evidence quote. Python first builds a small set of exact, bounded excerpts from each directly fetched candidate page for each source-independent held claim. Only excerpts that can satisfy the existing conservative lexical-overlap gate are exposed to Gemini. Gemini returns only an existing `claimId`, `sourceId`, `spanId`, and relation; Python resolves the exact excerpt, re-checks pair identity, source independence, exact numeric grounding, and overlap before adding any corroborating claim. This removes free-form quote drift without weakening the support gate or adding extra API calls. A directly fetched page may support another held claim from the same game only when its site is independent for that claim. All V52.4 outputs remain quarantine-only with `publicationWrites: 0`.

### V52.5 — bounded paraphrase corroboration with second semantic review
V52.5 separates *retrieving a potentially relevant exact-source span* from *accepting it as corroboration*. The old >=35% lexical-overlap path remains unchanged. When a directly fetched independent source shares only a deterministic claim-derived content anchor (for example, the same game object but different wording), Python may expose a bounded exact span to Gemini, but any support/contradict decision from that weaker anchor path must survive a second, separately prompted Gemini confirmation before it can be appended to the quarantined corroborated claim set. Generic guide vocabulary alone (e.g. only "攻略/達成/条件/報酬") cannot create an eligible anchor. Numeric support still requires exact token grounding, all claim/source/span identities are fixed by Python, same-site pairs remain excluded, API calls remain bounded, and publication writes remain zero.

### V52.6 — pair-complete claim-scoped corroboration classification
V52.6 keeps every V52.5 acceptance threshold intact but changes how the first Gemini classification pass is scheduled. Instead of one game-wide prompt where the model may return only a few of many eligible source/claim pairs, each held claim is classified in its own bounded prompt. Python provides an explicit `pairTasks` list and asks for exactly one decision per independent source pair, while continuing to require an existing Python-created span ID. Missing pair decisions are counted and held rather than inferred. Cross-claim tuples that were not requested by the current prompt are rejected before they can affect corroboration. `diagnosticCounts` now exposes classification calls, expected/returned/missing pair tasks, duplicate rows, and AI-budget exhaustion. The default corroboration AI-call budget is 8, all failures remain fail-closed, and publication writes remain zero.
### V52.7 — balanced claim-targeted corroboration discovery
V52.7 keeps all V52.6 support/contradiction acceptance rules unchanged and improves only URL discovery before direct retrieval. Each held claim may use a bounded second Tavily query built from the game name, exact numeric tokens, and deterministic non-generic claim terms. Search titles/snippets are used only to rank which URLs deserve the limited direct-fetch budget; they never become evidence, are never sufficient for support, and are not persisted as evidence text.

Discovery results from all held claims are canonicalized and deduplicated before retrieval. A round-robin ranked selector gives each held claim a fair chance at the global direct-fetch cap and preserves the existing per-claim result bound, preventing the first claim or first query from monopolizing retrieval. A URL that is the existing source site for the query's original claim may be retained only when it is independently eligible for another held claim, and the later per-claim independence gate still applies before any evidence span is exposed to Gemini. Production defaults are at most 2 searches per held claim, 8 corroboration search calls per run, 4 selected discovery URLs per claim, and 12 direct fetches per run. Publication writes remain zero.

### V52.8 — adaptive direct-text backfill
V52.8 keeps the V52.7 two-query discovery strategy and every V52.6/V52.5 acceptance gate unchanged, but reallocates the same bounded direct-fetch budget using information from the pages themselves. Each held claim gets one initial ranked fetch opportunity. After those direct fetches are target-confirmed, Python checks the fetched text with the existing deterministic span/overlap logic. Claims that still lack a strict independent direct-text match receive backfill priority for the remaining fetch slots; search titles and snippets do not determine this state and remain non-evidentiary.

The allocator re-checks each page's source-site independence for the specific claim before treating it as a strict/anchor hit. If every held claim already has a strict page, the remaining bounded fetch budget is still used in balanced exploration so possible contradictions are not hidden by early stopping. Production caps remain unchanged (including at most 12 corroboration direct fetches and the existing per-claim bound), AI classification/review behavior is unchanged, and all outputs remain quarantine-only with `publicationWrites: 0`.

#### Phase 4 V50.2 bounded extraction retry
V50.2 distinguishes a legitimate zero-claim result from a transient Gemini outage. Claim extraction may retry once per game only for bounded retryable failures such as network/timeout errors, HTTP 429/retryable 5xx/408 responses, invalid Gemini response formatting, or a malformed `claims` payload. Authentication and other non-retryable request errors are not retried. The status artifact reports actual AI attempts/retries and safe error categories without exposing raw response text or secrets. If the second attempt still fails, the extraction step exits non-zero after writing its quarantine/status files, so downstream V51/V52 stages cannot silently interpret an API outage as "no claims". The workflow still uploads the available quarantine artifact even on that failure. Public data is never written.

### V52.9 — bounded in-run corroboration batches
V52.9 keeps the V52.8 discovery, direct-text backfill, classification, semantic review, numeric grounding, source-independence, and publication gates unchanged for each individual batch. The production entry point now coordinates up to three batches inside the same manual workflow execution. With the current four-claim batch size, ten held claims are therefore attempted as 4 + 4 + 2 without relying on cross-run state.

After each batch, Python re-runs the deterministic V51 gate against the merged quarantine claim set. The next batch selects only held claim identities that have not already been attempted in the current workflow, so an unresolved first-batch claim cannot consume the next batch again. This is intentionally in-run only: no cursor or research state is written back to the repository. Existing per-batch caps are preserved; three batches are the hard coordinator maximum, so search/fetch/AI work remains bounded and `publicationWrites` stays 0. The status artifact exposes `batchesExecuted`, `batchSize`, `inputHeldClaims`, and `remainingHeldClaimsUnattempted` for live audit.


#### Phase 4 V50.3 atomic claim extraction
V50.3 keeps the V50.2 retry/fail-visible behavior and all evidence grounding rules, but tightens the extraction contract to one independently corroboratable proposition per claim. The prompt explicitly separates factual/mechanical statements from recommendations and avoids bundled multi-action advice; Python additionally rejects obvious mixed fact+advice, bundled-advice, and overlong claims instead of sending them downstream. Multiple atomic claims may cite the same literal source quote when that quote genuinely supports each proposition. No support threshold is relaxed and publication remains disabled.

### PHASE 4 V53 — poikatsu-first draft research + X (Twitter) experience discovery
V53 runs only after the post-corroboration V51 gate. Factual draft sections are assembled exclusively from `supported_quarantine` decisions; held or conflicting claims cannot enter verified article material. The draft is explicitly framed around point-reward offer completion rather than general game play, and reports missing coverage for offer conditions, completion timeline, priority/efficiency, and bottleneck/resource guidance instead of inventing them.

V53 also performs bounded `site:x.com` searches for public player experiences. Search titles/snippets remain discovery-only. A post is retained only when its X/Twitter status page can be fetched directly and the fetched page itself contains the target game plus poikatsu/achievement context. X posts stay in a separate `single_public_post_anecdote` quarantine lane and are never promoted to verified factual claims by V53. Outputs are `data/poi_guide_draft.json` and `data/poi_guide_draft_status.json`; public site files remain untouched and `publicationWrites` stays `0`.
