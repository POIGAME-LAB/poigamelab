# 1:17 JST daily pipeline — implementation boundary (2026-09-15)

## Implemented in the scheduled run

1. Restore large discovery/history state from R2; repository public values remain the fallback.
2. Fetch each first-party URL once and share success/failure cache across existing-offer checks and new-game discovery.
3. Discover new names from the same listing snapshots, require two independent registered source families, inspect detail pages, and rank at most five reviewed candidates by explicit yen value.
4. Update an existing published StepUp row only for a complete current Warau or Chobirich parser snapshot. The offer identity, game, OS, point/yen conversion, step sum, all step conditions, full terms, explicit deadlines, registered HTTPS URL, and evidence fingerprint must agree. Warau additionally requires its current first-party 1 pt = 1 yen help page in the same run.
5. Keep every old row on fetch, parsing, conversion, identity, completeness, or concurrent-write failure. Unsupported sources remain review-only.
6. Append history, create compact public monitors, build the real Pages artifact, then validate existing-row preservation, keys, amounts, conditions, URLs, catalog references, public/private separation, and byte-for-byte artifact data.
7. Only after validation, archive high-volume state and evidence to R2 and commit compact public data to GitHub. A non-main run or an advanced remote main is rejected; no automatic rebase is performed.

All existing game pages, top, comparison, detail, and guide pages read `data/published_offers.csv`. Guide pages now append a “現在の確認済み案件” block from the same data; historical player spend/reward prose is not rewritten.

## Deliberate publication holds

The daily run can find and rank new candidates but does **not** publish five new games by itself. The current free/API-free environment cannot reliably do all of the following with deterministic evidence: search authenticated/blocked X and Instagram content, recognize the same person across services, verify statements inside video, establish image reuse rights, and write a factually sourced guide. Query strings are preparation metadata, not completed research. Treating them as research would violate the no-guessing and no-duplicate-person rules.

The existing Phase 3/4 research workflows remain manual quarantine paths and use configured external APIs; they are not invoked by the 1:17 workflow. The old automatic adoption trigger is disabled. A safe alternative is: prepare five reviewed content packages outside Actions (source URLs, deduplicated player identities, progress facts, guide copy, licensed image), then run the deterministic adoption and Pages gates once. Until such packages exist, candidates stay unpublished.

## Current coverage limits

- Structured automatic amount/condition publication: Warau and Chobirich complete StepUp contracts only.
- Chobirich scheduled fetching is currently disabled because its live retrieval is not reliable, so its stored values are preserved rather than refreshed.
- Moppy, Hapitas, COINCOME, PointTown, EC Navi, Amefuri, and Gendama evidence is collected/reviewed where supported, but not promoted automatically because their parser contracts do not yet prove a complete publication snapshot.
- “Top five” means the five highest explicit-yen values among reviewed, two-site-confirmed candidates within the configured scan/detail budgets—not a claim about every offer on the entire internet.
