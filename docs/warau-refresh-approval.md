# Warau refresh: reviewed baseline contract

The refresh runner may renew only `updatedAt`, and only for an existing verified
Warau offer whose full freshly parsed evidence and published row match an explicit
reviewed baseline. It never changes rewards, terms, OS, URLs or verification flags,
and never creates an offer or an approval. Other sites remain discovery-only.

## Read-only audit, 2026-09-03

Seven direct public HTTP requests plus one saved response covered the eight
published Warau rows. These are observations, not approvals or a global conclusion
that a game has no offers.

| Game | Offer ID | Stored OS | Observed result | Hold |
| --- | --- | --- | --- | --- |
| Township | 204645 | Android | 9 steps, 21,670 pt; same ID/OS/amount | Stored absolute deadline 2026-11-01 is not supported by the inspected terms; terms specify 60 days from installation. |
| Township | 204643 | iOS | 9 steps, 16,760 pt; same ID/OS/amount | Same deadline issue. |
| きのこ伝説 | 205817 | Android | 11 steps, 18,800 pt; same ID/OS/amount | Published summary does not enumerate the purchase-dependent steps or 30/40/45-day limits. Review/enrich the summary before approval. |
| きのこ伝説 | 205816 | iOS | 11 steps, 22,000 pt; same ID/OS/amount | Same summary issue; per-step rewards differ by OS. |
| ホワイトアウト・サバイバル | 205389 | Android | Unavailable page at this URL | Do not transfer approval to recommended offers. |
| ホワイトアウト・サバイバル | 205390 | iOS | Unavailable page at this URL | Do not transfer approval to recommended offers. |
| メメントモリ | 205975 | Android | Unavailable page in saved response | Do not transfer approval to recommended offers. |
| メメントモリ | 206035 | iOS | Unavailable page at this URL | Do not transfer approval to recommended offers. |

The point source is the canonical Warau detail URL with the listed `point_id`:
`https://www.warau.jp/contents/point/pointEntrance.php?point_id=...`.
The official [exchange-rate help](https://www.warau.jp/help/qa/128/), checked on
2026-09-03, gives a base value of 1 pt = 1 yen. This is not a promise of net cash:
redemption destinations, fees and mile conversions can differ. The parser always
preserves the observed `pt` unit; conversion requires separate review.

## Proposed corrections after the audit

The review branch now changes exactly four published rows. Township's two
deadline fields state 60 days from installation instead of the unsupported
absolute date. Kinoko's two condition summaries enumerate all 11 steps, including
cash purchases, the level-100 prerequisite before the 3,200-yen purchase, and
30/40/45-day limits. The four manual check dates are 2026-09-03. Rewards, identities,
OS, verified flags and all other rows are unchanged; none of the unavailable rows
was removed or refreshed.

`data/warau_baseline_candidates.json` records the four revised-row fingerprints
and corresponding inspected evidence fingerprints. Every candidate explicitly has
`approved: false`. This is the historical candidate snapshot, not the current
approval status. Its `reviewed_registry_added` status points to the separate
reviewed registry. The refresh runner does not read this candidate file.

## Authorized seven-day enrollment (review branch only)

After reviewing the corrections and offline validation, the maintainer explicitly
authorized adding four exact-match, date-only approvals with a seven-day validity
window to the PR. `config/approved_offer_baselines.json` contains exactly those
four entries: Township IDs 204645/204643 and Kinoko IDs 205817/205816. The other
four Warau rows remain unapproved. Codex performed the evidence review; the
maintainer authorized the enrollment scope in ChatGPT. The record does not claim
that the maintainer independently inspected every source page.

The shared window is **2026-09-03 18:48:47 JST (inclusive) through 2026-09-10
18:48:47 JST (exclusive)**, stored as timezone-aware UTC timestamps. These are
fixed approval times, not relative to merge or the first scheduled run. A delayed
merge does not extend the window. Expiration or any evidence change requires
separate review; the system must not renew approval automatically.

The same-day saved official evidence and reviewed point conversion were reused;
no additional source requests were made for enrollment. Every actual refresh must
still fetch current evidence and match both fingerprints before updating a date.

**These approvals and data corrections are PR changes, not a merge or a live
deployment. No publication workflow was run. If separately merged, the existing
daily workflow can use these approvals until expiry; this enrollment does not
authorize a merge, a manual production run or a schedule change.**

## Approval input

The optional `config/approved_offer_baselines.json` is a maintainer-reviewed input,
not a collector output. Missing input means no approvals. Invalid JSON, schema or
duplicate offer keys abort before collection/publication. A review-queue entry is
never an approval, including when it has matching amounts or fingerprints.

Each record in `{"schemaVersion": 1, "approvals": [...]}` contains:

- `offerKey`, `game`, `source: "warau"`, `approved: true` (boolean).
- `reviewedBy`: a nonempty reviewer description; never fabricate user sign-off.
- `reviewedAt`, `expiresAt`: timezone-aware ISO timestamps; an explicit approval
  window. Missing, future, invalid or expired approval is held for review.
- `publishedRowFingerprint`: `published_row_fingerprint(row)` over every published
  field except `updatedAt`. First review the actual summary/deadline against the
  full step list and conditions; hashing is not a substitute for that review.
- `parserVersion: "warau-stepup-v1"`, `evidenceFingerprint`: from the inspected
  source evidence. Conditions, exclusions, per-step amounts, OS and total are
  included; recommendations are not. Parser-version changes require reapproval.
- `unitConversion`: `{"sourceUnit":"pt","targetUnit":"JPY","yenPerPoint":1,
  "evidenceUrl":"https://www.warau.jp/help/qa/128/"}`. Check that official evidence
  is still applicable when approving or renewing the approval window.

Do not automatically approve the first collected snapshot. Do not populate an
approval from a newly seen offer ID or a guessed correspondence between games.
Approval must be separately reviewed and submitted through the normal PR process.

## Runtime checks

Source parsing must succeed; current canonical/final/source URLs identify the same
offer; the row is already verified and has unique offer identity/key. Source
fingerprint, parser version, published-row fingerprint, OS, explicit point unit,
reviewed conversion and reward must all match. An expired absolute published
deadline is also rejected. A failure or any changed term preserves the old row.

A successful check updates the date in JST. Rechecking on the same JST day confirms
the row without rewriting its CSV. Other rows remain semantically unchanged. If
the CSV changed during collection, publication aborts instead of overwriting it.
Writers must still use the existing serialized workflow; this check is not a
replacement for coordination with other writers.

One confirmed site is still not a two-site comparison: `comparisonReady` follows
the existing configured minimum. No schedules or source scope are changed here.

## Tests

Run the three targeted Python suites and both existing frontend data/health tests.
Coverage includes expiry, future dates, changed terms/OS/reward/published row,
unsupported units, invalid/duplicate registries and rows, same-day idempotence,
JST rollover, concurrent CSV changes, no-approval preservation and all earlier
transport/parser regressions. The enrolled registry is tested in isolated copies;
live publication was not tested.

## Additional pre-approval validation, 2026-09-03

An offline replay of the eight saved official responses used the current game
aliases and known Warau URLs, with all output paths redirected to temporary
directories and outbound sockets disabled. Source and corrected-row fingerprints
matched all four candidates. The other four source pages remained unavailable.

Six scenarios passed: no approval (zero updates), test-only approval (four date-only
updates), repeat on the same JST day (CSV writer not invoked), expired test approval
(zero updates), one simulated timeout (three updates; failed row retained), and one
changed condition (three updates; changed row held for review). Each run used eight
distinct saved responses without duplicate fetches. A single confirmed site never
made a game comparison-ready. The fixture approval window and reviewer label were
test data only, never a maintainer approval or an enrollment recommendation.

Broader Phase 2 regression checks exposed three stale tests. The same three failures
were reproduced on the pre-PR main commit
`bb4275cf5254c924dc50cf0b90195182798897fe`. Two expected only the old iOS Warau ID
(one also assumed obsolete partial-fastpath opt-in); the third expected the previous
API scheduler configuration. Their assertions now reflect both registered Kinoko
IDs, default-off partial acceptance, bounded direct-fetch limits and preserved
publication safeguards. Production config and workflows were not changed.

After those test-only corrections, all 113 tests in the broader suite passed with
outbound sockets disabled. Both frontend data/health Node suites also passed.

Run the broader suite with:

```sh
python -m pytest -q tests/test_direct_offer_refresh_v1.py tests/test_phase2_identity_v20.py tests/test_phase2_fastpath_v21.py tests/test_phase2_parallel_v22.py tests/test_phase2_auto_refresh_v23.py tests/test_phase2_multigame.py tests/test_publisher.py
node tests/test_site_data_v24.js
node tests/test_site_health_v25.js
```

Desktop/mobile visual QA remains incomplete. The managed browser connected, but
opening the local preview was blocked (`ERR_BLOCKED_BY_CLIENT`). No alternate
network route or deployment was used to bypass that restriction. Merging and live
publication remain separate decisions from the authorized PR enrollment above.

## Validation of the enrolled registry

The exact PR registry was loaded through the runtime loader. Regression tests bind
all four entries to the reviewed candidate and published-row fingerprints, verify
an exact seven-day duration, and check acceptance at the start/last second plus
rejection before the start/at expiry/after expiry. Changed source terms, OS,
amounts or published summaries are rejected; date-only changes remain eligible.

The eight saved pages were also replayed using a byte-identical copy of the actual
registry in temporary directories, with outbound sockets disabled. Scenarios
cover missing approval, in-window enrollment, same-day idempotence, exact expiry,
before-window checks, the final valid second, one timeout, and one changed term.
No repository publication files or real approval records are written by a replay.

All 118 tests in the broader Python suite and both frontend data/health Node suites
passed after enrollment. The existing GitHub workflow runs the 100-test targeted
subset; its configuration is unchanged. Desktop/mobile visual QA and live
publication remain unperformed as noted above.
