# Hapitas review evidence

## Scope

Hapitas currently exposes useful first-party game offer pages through public
search indexing, including current POIGAME LAB targets. However, this project's
unattended direct-fetch path has not yet been demonstrated as a stable permitted
way to retrieve those detail/listing pages.

Hapitas is therefore kept as review-only for scheduled collection:
`scheduled_fetch_enabled: false`.

This does not delete existing published Hapitas rows, and it does not treat a
direct-fetch failure as evidence that an offer ended.

## Current first-party review targets observed on 2026-09-03

### Township

- Android: item ID 101453
  - current indexed shell: 38,738pt
  - 60-day StepUp
  - September 2026 super-sale amounts are shown on the official page
- iOS: item ID 101454
  - current indexed shell: 35,219pt
  - 60-day StepUp

Only the item identities are added to `game_targets.json`. The observed
amounts are not added to `published_offers.csv`.

### Kinoko Densetsu

- iOS: item ID 99850
  - current indexed shell: 4,416pt
- Android: item ID 100403
  - current indexed shell: 4,356pt

Only the item identities are added as review targets. No Hapitas Kinoko row is
published by this change.

### Working Heroes

The existing review targets remain:

- Android: item ID 101445
- iOS: item ID 101444

Current official indexed pages continue to show 11,502pt for these offers.
Existing published Working Heroes Hapitas rows are preserved byte-for-byte by
the scheduled-disabled source behavior.

## Why not auto-publish from indexed evidence

Current official Hapitas pages can change reward amounts during campaigns, and
the pages themselves tell users to confirm the latest information/conditions.
Township has already shown materially different indexed reward totals across
recent crawls.

Search-index visibility is therefore useful for manual review and target
discovery, but it is not treated as the scheduled source-of-truth transport.

## Re-enable gate

Scheduled Hapitas retrieval may be re-enabled only after a separate reviewed
change demonstrates:

1. stable first-party direct retrieval from the scheduled environment;
2. exact offer identity and OS binding;
3. reward-unit conversion;
4. complete StepUp terms and deadline binding;
5. transient-error behavior that preserves existing rows;
6. no automatic creation or reward mutation without reviewed authorization.

No production Hapitas request is performed by this change.
