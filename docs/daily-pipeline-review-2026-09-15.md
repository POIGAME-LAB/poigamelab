# 1:17 JST daily pipeline — implementation boundary (2026-09-16)

## Scheduled production path implemented on this branch

1. `Refresh comparison offers (API-free)` runs at `16:17 UTC` / `01:17 JST` on `main`.
2. The refresh restores high-growth state from R2, fetches first-party pages with one-run request caching, checks existing published offers, and discovers unlisted candidates from the same listing snapshots.
3. Existing published rows are fail-closed. Complete Warau / Chobirich StepUp snapshots may refresh reward + conditions + deadline together. Hapitas may refresh reward/date/source metadata only when exact offer identity, OS, `1pt=1JPY`, complete current evidence and fingerprint checks pass; the existing condition/deadline/type prose is preserved.
4. New-game review keeps ambiguous titles for verification and excludes only explicit likely-non-game candidates at that stage. A candidate must be confirmed on at least two independent registered source families and have an explicit yen value before it can rank.
5. The bounded review budget is 30 candidate groups / 120 detail inspections. Values from alternative sites or OS rows are never summed.
6. Ranking is fail-closed. If a required source scan is incomplete, a review/detail budget is exhausted, or source discovery hits a safety guard, `rankingComplete=false` and no new-game content queue is authorized for that day. Sources intentionally configured for bounded partial coverage are allowed when their configured scan completes normally.
7. When ranking is complete, at most five reviewed unlisted games are written to `data/new_game_content_queue.json` in reward-descending order. This handoff never authorizes publication by itself.
8. The Pages artifact is built and validated before R2 archive or Git commit. Existing-row preservation, offer keys, URLs, catalog references, public/private separation and frontend regressions are checked before any compact production output is pushed.

## Optional automatic research and publication chain

After a successful refresh on `main`, `Research top-five new games (quarantine)` can start automatically only when repository variable `ENABLE_NEW_GAME_CONTENT_RESEARCH == 'true'`.

For each queued game it performs bounded research across Web, X, YouTube, Instagram and verified point-site evidence. Search discovery is not treated as evidence: candidate URLs must be directly fetched and contain the target game. The research workflow has read-only repository permissions and cannot push production changes.

Grounded content synthesis is fail-closed. Numeric claims must exist in cited evidence, progress entries must come from directly fetched social/public-player sources, and unsupported or incomplete packages remain held. A neutral POIGAME LAB title-card SVG is generated locally from the game name, so unattended publication does not depend on third-party game artwork rights.

After a successful research run, `Publish researched top-five new games` can publish only when repository variable `ENABLE_NEW_GAME_AUTO_PUBLISH == 'true'`. It downloads the exact successful research artifact, verifies its SHA-256 bundle, rejects stale `main`, runs deterministic V29/V30 adoption and publication gates, builds the real Pages artifact, runs offline regressions, stages only approved production outputs and generated guide/image files, then pushes to `main`.

If the daily queue contains zero games, the research workflow exits before Tavily/Gemini/Firecrawl work and performs no paid research API calls.

## Deliberate holds and limits

- Moppy remains review-only for automatic reward publication because the public shell says applicable reward/conditions may differ at the downstream `POINT GET` destination.
- COINCOME, PointTown, EC Navi, Amefuri and Gendama structured evidence can support candidate/research verification where their contracts pass, but they are not automatically allowed to rewrite an existing public row unless a publication contract explicitly supports that source.
- X / Instagram / YouTube lanes may legitimately return zero usable direct sources. Missing evidence causes the content package to hold rather than inventing progress or guide claims.
- “Top five” means the highest explicit-yen values among two-source-confirmed candidates in a successfully completed configured daily scan. The system does not claim to enumerate every offer on the internet.

## Production activation state

This document describes the implementation on `feat/unified-daily-free-pipeline`. The branch validation workflow has passed syntax checks, offline new-game regressions, existing deployment regressions and a rehearsal of the exact Pages artifact build. Production activation still requires integrating the branch with the latest `main` without overwriting newer bot-generated data, then enabling the two repository variables above if unattended research and publication are desired.
