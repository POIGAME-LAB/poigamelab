# Launch data hygiene review — 2026-09-03

## Scope

This review removes four Warau rows that failed live first-party availability
checks immediately before launch and prevents the public site from reviving older
legacy `offers.csv` values when a managed game temporarily has zero verified
offers.

Affected historical Warau point IDs:

- MementoMori Android: 205975
- MementoMori iOS: 206035
- Whiteout Survival Android: 205389
- Whiteout Survival iOS: 205390

## Live read-only evidence

The repository's candidate-only Warau review tool was run through a GitHub
Actions job with `contents: read` permissions only.

Two entrypoint variants were checked:

1. the previously stored `ssl.warau.jp` URLs;
2. the equivalent `www.warau.jp` URLs using the same point IDs.

For all four identities, the strict Warau parser returned:

`state: unavailable`
`reason: source_offer_unavailable`

Both runs also completed the protected-file hash/diff proof successfully, so
`data/published_offers.csv`, `config/approved_offer_baselines.json`, and
`data/warau_baseline_candidates.json` remained unchanged by the live review.

Search-engine indexes may continue to show recently crawled copies after a live
first-party offer has ended. Launch publication therefore follows the direct
live first-party result rather than cached search snippets.

## Publication cleanup

The four ended Warau rows are removed from `data/published_offers.csv`.

Their known Warau detail URLs are also removed from
`config/game_targets.json`. Future Warau checks for these games must rediscover
a current first-party identity rather than repeatedly polling an ended offer ID.

Current offerwall/provider observations remain review-only under the existing
provider contracts and do not replace the removed direct offers automatically.

## Legacy fallback hardening

All five catalog games are managed by `config/refresh_policy.json`.

`site-data.js` now suppresses legacy `offers.csv` rows for any game listed in
that policy, even when the game has zero currently verified published rows.

If the refresh policy itself cannot be loaded, legacy rows fail closed and are
not shown. Verified published rows may still render.

This prevents a removed current offer from exposing an older placeholder amount
from August 2026.

For a managed game with zero verified offers, the detail page already renders:

`現在確認できる案件はありません。`

That is the intended launch behavior until a new reviewed offer is discovered.

## Safety boundary

This cleanup does not:

- create a new offer;
- promote search snippets or offerwall presence to publication;
- add a baseline approval;
- run a publication workflow;
- infer replacement reward amounts from cached search results.
