# Remaining offerwall provider review contracts

Reviewed on 2026-09-03.

This document covers the six remaining provider identities that were already
present in `offerwall_domains_discovered` but did not yet have a reviewed
provider contract.

All six remain `presence_only`. None is authorized for direct offerwall
requests or publication.

## MyChips

Presence domain: `cdn.mychips.io`

Official integration documentation:
- https://docs.mychips.io/webview-and-direct-link

Current WebView/direct-link documentation requires `content_id`, `user_id`,
and `webview` and recommends GAID/IDFA. Because reward attribution depends on
user/device context, POIGAME LAB records provider presence only.

## Zucks

Presence domain: `ow.z.mobu.jp`

Official support evidence:
- https://zucks.freshdesk.com/support/solutions/articles/157000368856--%E3%81%8A%E5%95%8F%E3%81%84%E5%90%88%E3%82%8F%E3%81%9B%E6%96%B9%E6%B3%95

The official support article gives an offerwall inquiry URL example on
`ow.z.mobu.jp` containing `user_id`. That is enough to classify the
offerwall as user-contextual for this project.

## GMO SmaAD

Presence domain: `wall.smaad.net`

Official service evidence:
- https://smaad.net/media/
- https://smaad.net/news/428/

Current official materials describe SmaAD Wall as a dedicated ad-list page
embedded in partner websites/apps, with SDK support. The reviewed material does
not establish an anonymous public campaign catalog suitable for unattended
evidence retrieval. This contract therefore uses the narrower reason
`anonymousPublicCatalogEstablished: false` rather than claiming a specific
user-ID URL format.

## TyrAds

Presence domain: `sdk.tyrads.com`

Official integration evidence:
- https://sdk-doc.tyrads.com/web-iframe/initialization
- https://sdk-doc.tyrads.com/android/initialization
- https://tyrads.com/tyrsdk-terms-of-service/en

Current TyrAds documentation shows web initialization with publisher
credentials and `userID`, while SDK documentation describes user/device
identifiers used for tracking and attribution. POIGAME LAB therefore records
provider presence only.

## Playtime by adjoe

Presence domain: `chobirich.playtimeweb.com`

Official integration evidence:
- https://docs.adjoe.io/rewarded-solutions/playtimeweb-for-ios/intro-to-playtimeweb/integrate-playtimeweb

Current PlaytimeWeb documentation requires `user_id` in the redirect URL and
recommends IDFA for attribution. The partner-specific PlaytimeWeb hostname is
therefore not treated as an anonymous public catalog.

## ayeT

Presence domain: `offerwall.ayet.io`

Official integration evidence:
- https://docs.ayetstudios.com/v/product-docs/offerwall/web-integrations/web-offerwall
- https://www.ayetstudios.com/openapi/publisher-doc

Current web-offerwall documentation requires an `externalIdentifier` for the
calling user. The Publisher API likewise exposes user/device-context parameters
for offer retrieval and attribution. POIGAME LAB therefore records passive
provider presence only.

## Repository invariant

Every domain in `offerwall_domains_discovered` must now have exactly one
reviewed provider contract in `config/offerwall_providers.json`.

Regression tests enforce:

- exact domain coverage;
- unique provider IDs and presence domains;
- `retrievalMode: presence_only`;
- `followExternalLinks: false`;
- `persist: provider_domain_only`;
- user-context flags where directly supported by official evidence.

This means a future newly discovered offerwall domain cannot silently remain a
mystery hostname. It must receive a reviewed provider contract before CI passes.
