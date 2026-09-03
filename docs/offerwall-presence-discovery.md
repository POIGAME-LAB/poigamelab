# Passive offerwall presence discovery

## Scope

This change detects whether a first-party point-site listing contains a
target-adjacent link to a previously known offerwall provider. It is presence
evidence only.

The scheduled collector does **not** follow an offerwall link, fetch an offerwall
page, save a tracking URL, infer a reward, create an offer, or mark a comparison
source confirmed from this signal.

## Privacy and transport contract

Offerwall presence detection runs only when the repository configuration exactly
requires all of the following:

- `enabled: true`;
- `follow_external_links: false`;
- `persist: provider_domain_only`;
- `require_target_context: true`.

If any part of that contract is missing or changed, detection fails closed.

Only HTTPS links on an exact hostname listed in
`offerwall_domains_discovered` are considered. Credentialed URLs and
non-standard ports are rejected. The detector requires the target game alias in
the link label or bounded surrounding first-party HTML context.

The only external value persisted is the normalized provider hostname, for
example `ow-gf-rewards.com`. Path, query, fragment, tracking parameters and
embedded user identifiers are discarded before anything reaches the review
queue. The external URL is never requested.

## Review behavior

When a target-adjacent known offerwall hostname is observed, the review queue
receives `offerwall_presence_candidate` with a `providerDomains` list. This is
not publication evidence and does not count toward `standardConfirmed` or
`comparisonReady`.

If no first-party detail is available, the offerwall presence candidate replaces
a generic `discovery_required` item for that source/game pair so the review
queue records the more useful reason without claiming an offer amount or current
terms.

## Why

Some current game campaigns are surfaced through external offerwall providers
inside point sites. Following those links can involve tracking identifiers,
provider-specific access rules and a different evidence contract. This layer
therefore separates safe first-party presence detection from any future
provider-specific retrieval or publication logic.

Any future offerwall integration requires a separately reviewed provider-specific
design and explicit authorization. This change does not provide one.


## Same-card binding hardening

Presence is not inferred from raw character proximity across the whole listing.
The detector parses the first-party HTML tree and accepts an offerwall link only
when the target alias is present in the anchor label or within a bounded ancestor
container for that link. Traversal stops after four ancestor levels and rejects
containers larger than 1,400 visible characters.

This prevents a dense listing from attaching Game A to an offerwall link that
actually belongs to the adjacent Game B card. Regression tests cover adjacent
cards, nested links within the same card, and oversized page-wide containers.
