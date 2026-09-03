# Moppy shell evidence review

## Scope

This change adds a source-specific parser for the public Moppy offer shell.
It remains review-only. It does not authorize Moppy freshness updates, reward
changes, new published rows, or automatic comparison readiness.

## Current Whiteout observations, 2026-09-03

Current official public pages were found for both Whiteout Survival variants:

- Android: offer ID 160375, displayed 6,119P.
- iOS: offer ID 160371, displayed 7,932P.

The Android published row already uses ID 160375 and 6,119. Its published date is
not refreshed by this change.

The iOS ID 160371 is added only to `game_targets.json` as a known review target.
It is not added to `published_offers.csv`.

## Critical source rule

Moppy's own Whiteout detail page states that the points and conditions shown on
the page reached after tapping `POINT GET` apply when they differ from the
public shell page. The shell also instructs users to confirm each StepUp
milestone on that destination.

Therefore a shell match alone is not authoritative enough for automatic
publication. The parser records `downstreamTermsRequired: true` and the runtime
continues to hold Moppy as `source_refresh_not_enabled`.

## Parser contract

The shell is `parsed` only when:

1. requested and final URLs are HTTPS on exactly `pc.moppy.jp`;
2. the path is exactly `/ad/detail.php`;
3. exactly one numeric identity is supplied using either `site_id` or `s_id`;
4. an optional canonical URL, when present, resolves to the same identity;
5. exactly one h1 matches the target and identifies one of Android or iOS;
6. exactly one displayed `P` reward occurs in the bounded offer header;
7. the page explicitly states the base `1ポイント=1円` rate;
8. the conditions include an acquisition section, a result-reception period,
   and a caution/rejection section;
9. the page explicitly refers to `POINT GET` and a destination page;
10. the bounded header and full shell conditions are fingerprinted.

Ambiguous rewards, OS labels, URL identities, missing conversion evidence,
missing conditions, or absent downstream instructions are review cases.

## Publication gate

Even if the public shell exactly matches the stored Android row, the main
refresh loop does not authorize Moppy publication. A future Moppy approval must
additionally bind the authoritative `POINT GET` destination, StepUp amounts,
deadline origin, and complete downstream terms.

## Validation

Regression tests cover `site_id`/`s_id` normalization, redirect identity,
reward ambiguity, OS ambiguity, conversion evidence, downstream-term presence,
terms changes, transport failures, and the publication-disabled gate.

No production collector/AI API call or live publication workflow dispatch is
part of this change.


## Current MementoMori review targets, 2026-09-03

Fresh public Moppy pages were found for a newer 45-day MementoMori StepUp pair:

- Android: offer ID 160690, displayed 9,661P, 45-day StepUp.
- iOS: offer ID 160688, displayed 13,354P, 45-day StepUp.

Older 30-day MementoMori pages with IDs 161975/161974 remain visible in search
indexes, but this review target update intentionally records only the fresher
45-day pair. The two new IDs are added to `game_targets.json` only. They are not
added to `published_offers.csv`, and their displayed shell rewards are not used
to refresh publication because the Moppy shell still requires authoritative
`POINT GET` destination terms.

This is target discovery, not publication approval.


## Downstream provider identity from first-party shell text

Current official Moppy shell pages for the reviewed AppDriver-backed game offers
explicitly direct point-missing inquiries to the "アプリドライブ" site. This is
first-party Moppy evidence and does not require opening a POINT GET destination.

The reviewed AppDriver provider contract therefore includes the first-party
labels `アプリドライブ` and `AppDriver`. During structured Moppy review, when
a parsed shell both requires downstream terms and contains a reviewed provider
label, the review evidence may add `downstreamProviderCandidates`.

This enrichment is identity-only:

- the provider remains `presence_only`;
- no AppDriver URL is requested;
- no downstream reward or milestone is inferred;
- no source is confirmed;
- no publication field is changed;
- the Moppy shell's existing downstream-terms gate remains in force.

The provider label is already part of the bounded Moppy terms text and therefore
covered by the existing shell evidence fingerprint.
