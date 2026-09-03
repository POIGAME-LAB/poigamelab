# COINCOME structured review evidence

## Scope

This change adds a source-specific COINCOME detail parser for review evidence.
It does not authorize COINCOME publication, freshness-date updates, new offers,
reward changes, OS corrections, or automatic two-source comparison readiness.

The existing COINCOME published rows remain unchanged.

## Current public observations, 2026-09-03

COINCOME's public site and current non-game detail pages remain readable. Current
detail pages expose a recognizable sequence around the conditions area:

- offer title and displayed yen amount near the top;
- `ストア概要` / `概要`;
- `適用端末`;
- `キャッシュバック条件`;
- `承認条件`;
- `■ポイント獲得条件`;
- `否認条件`.

The site also states that the displayed amount or percentage is returned as CIM.
Its public home page describes CIM points as displayed in yen-equivalent terms
and pegged to Japanese yen for electronic-money / point exchange. This parser
records the observed amount as `JPY-equivalent`; it does not itself authorize a
conversion contract for publication.

Current public examples can display both a former and a current yen amount near
the offer header. The parser therefore refuses pages with more than one distinct
header yen amount. It never assumes that the first or largest number is the
current reward.

The repository's existing game URLs were not replaced in this change. During the
September 3 review, current search did not surface Township, Kinoko, Whiteout or
MementoMori detail replacements, and at least one existing game detail URL
returned 404 through public retrieval. A fetch failure is retained as a fetch
diagnostic, not converted into a claim that the game has no COINCOME offer.

## Parser contract

A COINCOME detail page is `parsed` only when all of the following hold:

1. requested and final URLs are HTTPS on exactly `cimcome.jp`;
2. the path is exactly `/campaigns/details/<numeric id>`, without credentials,
   unusual ports, suffix paths, or query strings;
3. an optional canonical URL, when present, resolves to the same numeric ID;
4. one target alias is present;
5. the target header has an explicit `ストア概要` or `概要` boundary;
6. exactly one distinct yen amount appears in that offer header;
7. exactly one of Android or iOS is explicitly present before the conditions
   block;
8. the full conditions block includes, in order, `適用端末`,
   `キャッシュバック条件`, `承認条件`, `ポイント獲得条件`, and
   `否認条件`;
9. the full header and conditions block are fingerprinted.

Anything ambiguous remains `review_required`. An explicit not-found page can be
recorded as unavailable, while transport-level 404/403 responses remain fetch
failures. Neither state deletes or edits existing publication rows.

## Publication gate

`inspect_detail()` now dispatches COINCOME through the structured parser, but
the main refresh loop still enables date refresh only for reviewed Warau
baselines. Even a fabricated COINCOME approval entry therefore remains held as
`source_refresh_not_enabled`.

A future COINCOME auto-refresh change must separately establish:

- current game detail identities for each OS;
- reliable direct retrieval of those identities;
- the exact meaning and conversion of the displayed CIM amount for the
  publication field;
- complete StepUp terms and deadline origin;
- reviewed published-row fingerprints;
- explicit maintainer authorization.

## Validation

Synthetic regression fixtures cover exact identity, canonical mismatch, ambiguous
old/current reward displays, missing header boundaries, OS ambiguity, incomplete
conditions, changed-term fingerprints, explicit not-found content, transport 404
retention, and the publication-disabled gate.

No production collector/AI API call, live publication workflow dispatch, or
published CSV edit is part of this change.
