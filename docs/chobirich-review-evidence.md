# Chobirich: structured evidence, not approved refresh

## Scope

The numbered-StepUp parser extracts review evidence only. It does not change any
published row, enroll Chobirich approvals, add a browser collector, or change the
six-site policy/schedule. Warau's four approved fingerprints and expiry are
unchanged. One verified site still does not constitute a two-site comparison.

## Inspection on 2026-09-03

The configured direct HTTP fetcher returned 404 for IDs 1896275 and 1883822 (one
fetch attempt per URL, without application-level retries). Search could read their page content, but those
results alone do not prove present availability. The public managed browser then
successfully rendered [1896275](https://www.chobirich.com/ad_details/1896275).
Its exact canonical identity, explicit point/yen totals and terms were inspected
without signing in, following advertising links or submitting anything.

For that one browser-observed page:

| Item | Observation | Published-row issue |
| --- | --- | --- |
| Game / identity | Kinoko, ID 1896275 | Same offer URL |
| Platform | Android-specific QR action | Stored platform is unknown; do not infer OS from generic Apple warnings |
| Total | 13,409 points and explicit 13,409-yen equivalent | Stored amount matches; this alone is not verification |
| Steps | 11; individual amounts sum to 13,409 | Summary needs review of purchase prerequisites |
| Timing | 30/40/45 days from advertising click, depending on step | Stored deadline omits the starting event |

The source has purchase exclusions, a level-100 prerequisite for the 3,200-yen
purchase, and installation-date eligibility clauses. They remain in the full
source fingerprint. No date-only approval should be granted until the published
summary, OS and deadline have been separately reviewed and the retrieval path is
reliable. No published data was corrected in this change.

The official [rate-change notice](https://www.chobirich.com/lp/open/point_rate_update)
and [help entry](https://help.chobirich.com/0353093ce06c48718a8fdcf7cbdda4f4)
confirm a base rate of 1 point = 1 yen since June 22, 2026. Older 2-points-per-yen
examples must not be applied to current offers. The parser requires the displayed
yen total as a separate cross-check and holds unsupported/contradictory formats;
it does not calculate a redemption entitlement.

Web lookup of Township 1894712 returned 403, and 1896200 returned an internal
fetch error. Neither result establishes that an offer ended. No browser attempt
was made for those failed web lookups. The cause of the direct-HTTP/browser
discrepancy is unconfirmed; do not label it bot detection without site evidence.

## Parser contract

- Exact requested/final/canonical numeric identity on registered HTTPS detail
  paths; no credentials, unusual ports, redirect-handler paths or path suffixes.
- Exactly one main/h1, explicit `item_yen` summary and adjacent point total.
- Only the observed Android/iOS-specific QR button label supplies OS. Repeated
  identical buttons are fine; missing or conflicting labels are held.
- Exactly one `ad-requirement` block with achievement heading and paragraph.
  Numbered lines must start at one, be consecutive and complete, use point units,
  have distinct conditions and sum to both displayed totals. Preserve line breaks,
  click-versus-install origin, purchase ordering and complete remaining terms.
- Missing terms, rendered-only elements absent from raw HTML, decimal-point
  variants or other unsupported layouts are review cases, never partial success.
- Even a supplied Chobirich approval record is held as `source_refresh_not_enabled`.
  No fallthrough to a page-wide number match and no automatic OS/key correction.

The inspected local excerpt is browser-rendered DOM, not a successful raw HTTP
response. It demonstrates parsing of that structure, not scheduled retrieval.
Synthetic fixtures reproduce structure without publishing copied full terms.

## Validation and remaining work

The inspected DOM excerpt parses as 11 Android steps totaling 13,409 points/yen.
The parser extension passed 153 broader Python cases, including 35 new parser and
review-only cases; the then-current GitHub targeted subset contained 135 cases.
Tests cover malformed/missing totals, obsolete conversion, incomplete steps,
wrong identity, misleading OS text, changed terms and 404 retention. The Warau
offline replay remains unchanged and no production AI/collector calls were made.

Still needed: establish a reliable permitted direct retrieval path, inspect the
other variants, review/correct the existing OS and terms, and obtain separate
approval for any future Chobirich freshness updates. This change does not make
automatic two-site comparison ready. The local site's prior PC/mobile visual-QA
limitation and PR merge approval requirement remain.

## Retrieval diagnosis follow-up, 2026-09-03

One further direct fetch of the same 1896275 URL, with the existing fetcher and
unchanged request headers, again returned HTTP 404. Its final URL was unchanged,
its content type was `text/plain; charset=UTF-8`, and its body said the page could
not be found. This establishes the observed response, not why it differs from
the earlier public browser observation. No User-Agent rotation, credentials,
proxy, alternate host, browser retry or paid collector was introduced.

Targeted official-help searches did not establish a cause or a supported
automated retrieval method. The official terms link returned 403 through web
lookup; it was not retried through another route. Automation permission has not
been established by this investigation, and Chobirich refresh remains disabled.
The existing published OS and terms still need separate review/correction.

The follow-up found a local diagnostic gap: listing failures were discarded when
known detail URLs existed. The runner now retains `listing_fetch_failed` review
items for those listings while independently inspecting the known URLs. Without
detail URLs, the existing `discovery_required` / `listingErrors` format remains.
This does not add JSON keys or change CSV columns, approval logic or fetch limits.

Existing error strings now contain safe categories such as `http_status_404`,
`http_status_429`, `timeout`, `network_error` and guard rejection codes. HTTP errors
are classified before their `URLError` parent. Unknown exception text and HTTP
error bodies are not copied into diagnostics. These categories describe a fetch,
not whether an offer ended. Error responses are closed before caching failures;
an I/O error during close does not discard the original failure or cause retries.

Validation added 21 cases (174 broader Python cases total; 156 in the unchanged
CI subset), covering known/unknown detail URLs, 404/429, raw-text omission, response
closure, failed-close handling, cross-game cache reuse, review counts, data
preservation and successful approved Warau detail checks despite listing failure.
All broader tests ran with outbound sockets blocked. Both frontend suites and
the eight saved-evidence Warau replay scenarios passed. Published data, the four
actual approvals, schedules and frontend files were unchanged. No live publication
run or production AI/collector API call was made; PC/mobile visual QA remains
incomplete.
