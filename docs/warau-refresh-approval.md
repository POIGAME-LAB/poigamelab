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

**No production approval registry is added by this change. All eight rows remain
unapproved for automatic freshness updates. Published CSVs are unchanged.**

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
transport/parser regressions. Real approvals and live publication were not tested.
