# Design notes

Each section is a decision, the alternative I rejected, and where to read the code.

## Two kinds of signal, labelled as such

Every signal carries a `basis`. **Mechanical** signals report a plain fact: robots.txt does or does not forbid a named crawler from the page. **Heuristic** signals are rules of thumb about what probably makes a page easy to quote (structured data, question headings with direct answers, concrete detail, authorship, structure, sources, text present without scripts).

Nobody, including this tool, has measured how much any heuristic signal changes whether an answer engine cites a page. The weights ([`signals/context.py`](../src/aeo_audit/signals/context.py)) are my judgment, and the report footer says so. An earlier version of this scorer claimed that Q&A-shaped pages are "5x more likely to be cited" and that its weights came from case studies. I could not source either claim, so they are gone. Fixes are ordered with mechanical blockers first, then by points available, because a blocked crawler is a fact and the rest are bets.

## A hand-written robots.txt matcher

`urllib.robotparser` predates RFC 9309. It has no `*` or `$` in paths and it takes the first matching rule instead of the longest. Both change whether a crawler may fetch a page, which is the one question the mechanical signal answers. [`robots.py`](../src/aeo_audit/robots.py) implements the RFC rules directly: a group is chosen by product token (a named group does not inherit the `*` group), repeated groups for one agent are merged, the longest matching pattern wins, and `Allow` wins a tie. `tests/test_robots.py` covers each rule, including the order-independence property.

Not implemented: percent-encoding normalisation of paths, and `Crawl-delay` / `Sitemap` (ignored, as the RFC allows).

## Counting only the crawlers that matter for being cited

[`agents.py`](../src/aeo_audit/agents.py) lists AI crawlers with a role: `search` (builds an answer index), `user` (fetches a page when a person asks) or `training`. Blocking a training crawler is a legitimate policy and does not stop a page appearing in a live answer, so it is reported but never penalised. The list is data that goes stale; each vendor documents its own tokens.

A block is always surfaced as a fix even when the signal's score is above the usual threshold, and the report headline says so, so an "A" page that blocks two search crawlers is not described as simply well set up.

## A fetcher that cannot be pointed at your own network

A tool that fetches user-supplied URLs is a server-side request forgery primitive unless each request is checked ([`fetch.py`](../src/aeo_audit/fetch.py)):

- The URL must be http(s), without embedded credentials.
- Every hop of a redirect chain is resolved and every returned address must be globally routable (`ipaddress.is_global`, with IPv4-mapped IPv6 unwrapped). One private address among several is enough to refuse.
- The socket is opened to the vetted IP, not to the host name, and TLS still verifies the original name. Resolving once and connecting to that answer closes the gap DNS rebinding relies on. A test asserts the host is resolved exactly once per hop and that the `Host` header still carries the name.
- Responses are size-capped, sent with `Accept-Encoding: identity` (no decompression bombs), and bounded by a total deadline, not just a per-read timeout.
- Each vetted address is tried in turn, so `localhost` resolving to `::1` first does not fail a page served on IPv4.

`--allow-private` exists for auditing a site on your own machine and is off by default.

## Static HTML only, on purpose

The page is parsed with the standard library's `html.parser`; no JavaScript runs. That shows the page as a crawler that does not execute scripts would see it. Whether a given vendor's crawler renders JavaScript is not something I can verify, so the `renderability` signal is labelled heuristic and its explanation says exactly that.

## Metamorphic tests instead of ground truth

There is no dataset to validate scores against, so the tests check direction instead ([`tests/test_metamorphic.py`](../tests/test_metamorphic.py)). Starting from the well-built fixture, Hypothesis applies random orderings of degrading edits (strip the JSON-LD, remove the author, flatten the headings, unwrap the links, block a crawler, and so on); the score must never go up after any step. Starting from the weak fixture, it applies markup-only improvements; the score must never go down. A final test proves each mutation actually changes the page, so a typo in a regex cannot make a test pass vacuously.

I also broke six rules by hand (longest-match, the private-address check, redirect-hop checking, group inheritance, the FAQ-matches-page check, and which crawler roles count) and the suite failed for each. That was a manual spot check, not a mutation-testing run.

## Honest FAQ markup

A `FAQPage` earns credit only for questions that have an accepted answer and whose text also appears on the page. Markup describing content the page does not show earns nothing, which matches search engines' published guidance that structured data must reflect visible content.
