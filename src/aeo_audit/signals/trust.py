"""Who wrote it, when, and what it points to."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

from aeo_audit.model import Signal
from aeo_audit.signals.context import Context, make_signal

_BYLINE = re.compile(r"\b[Bb]y\s+[A-Z][\w'’.-]+(?:\s+[A-Z][\w'’.-]+){1,3}")
_PUBLISHED_META = (
    "article:published_time",
    "datepublished",
    "date",
    "dc.date",
    "og:published_time",
)
_MODIFIED_META = ("article:modified_time", "datemodified", "og:updated_time", "dc.date.modified")
_VAGUE_ANCHORS = frozenset(
    {"", "here", "click here", "read more", "more", "learn more", "link", "this", "website", "page"}
)
_SOCIAL_HOSTS = frozenset(
    {
        "facebook.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "instagram.com",
        "pinterest.com",
        "t.co",
        "wa.me",
        "reddit.com",
        "tiktok.com",
    }
)
_REFERENCE_HOSTS = frozenset({"doi.org", "arxiv.org", "pubmed.ncbi.nlm.nih.gov"})
_REFERENCE_SUFFIXES = (".gov", ".edu", ".int")


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _schema_values(ctx: Context, key: str) -> list[Any]:
    return [node[key] for node in ctx.page.nodes() if key in node]


def _declared_author(ctx: Context) -> str | None:
    meta = ctx.page.meta
    for key in ("author", "article:author"):
        if meta.get(key):
            return meta[key]
    for value in _schema_values(ctx, "author"):
        for item in value if isinstance(value, list) else [value]:
            candidate = item.get("name") if isinstance(item, dict) else item
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _has_profile_link(ctx: Context) -> bool:
    if any("author" in link.rel for link in ctx.page.links):
        return True
    for value in _schema_values(ctx, "author"):
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict) and (item.get("url") or item.get("sameAs")):
                return True
    return False


def authorship_freshness(ctx: Context) -> Signal:
    page = ctx.page
    author = _declared_author(ctx)
    byline = _BYLINE.search(page.text)
    profile = _has_profile_link(ctx)

    published = [_parse_date(page.meta.get(k)) for k in _PUBLISHED_META]
    published += [_parse_date(v) for v in _schema_values(ctx, "datePublished")]
    modified = [_parse_date(page.meta.get(k)) for k in _MODIFIED_META]
    modified += [_parse_date(v) for v in _schema_values(ctx, "dateModified")]
    fallback = [_parse_date(v) for v in page.times]
    has_published = any(published) or any(fallback)
    has_modified = any(modified)
    known = [d for d in (*published, *modified, *fallback) if d and d <= ctx.now]
    latest = max(known) if known else None

    points = 0
    evidence: list[str] = []
    if author:
        points += 35
        evidence.append(f"Author named in metadata: {author}")
    if byline:
        points += 15
        evidence.append(f"Visible byline: {byline.group(0)}")
    if profile:
        points += 10
        evidence.append("Author links to a profile (rel=author, url or sameAs)")
    if has_published:
        points += 20
    if has_modified:
        points += 10
    freshness = "no date found"
    if latest is not None:
        age_days = (ctx.now - latest).days
        freshness = f"latest date {latest:%Y-%m-%d} ({age_days} days old)"
        points += 20 if age_days <= 365 else 10 if age_days <= 730 else 0
        evidence.append(f"Latest date on the page: {latest:%Y-%m-%d}")

    who = "named author" if author else "visible byline only" if byline else "no author"
    return make_signal(
        "authorship_freshness",
        "Authorship and freshness",
        points,
        basis="heuristic",
        found=f"{who}; {freshness}.",
        evidence=tuple(evidence),
        why=(
            "Readers and systems that weigh trust look for who stands behind a page and whether "
            "it is current. A named author and visible dates are the plain, checkable version."
        ),
        fix=(
            "Show a real author byline and put the same author in metadata (meta author or "
            "JSON-LD), link it to a profile, and publish datePublished and dateModified. "
            "Update the page and its date when the facts change."
        ),
    )


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _is_social(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS)


def _is_reference(host: str) -> bool:
    return host in _REFERENCE_HOSTS or host.endswith(_REFERENCE_SUFFIXES)


def citations_links(ctx: Context) -> Signal:
    page = ctx.page
    own = _host(page.url)
    content = [link for link in page.links if link.in_content and "nofollow" not in link.rel]
    external = {_host(link.href) for link in content if _host(link.href) not in ("", own)}
    external = {host for host in external if not _is_social(host)}
    reference = {host for host in external if _is_reference(host)}
    internal = {
        urlsplit(link.href).path.rstrip("/") or "/" for link in content if _host(link.href) == own
    }
    descriptive = [
        link for link in content if link.text.strip().lower().rstrip(".!") not in _VAGUE_ANCHORS
    ]
    anchor_points = 20 * len(descriptive) / len(content) if content else 0.0
    score = (
        min(50, 10 * len(external) + 10 * len(reference))
        + min(30, 3 * len(internal))
        + anchor_points
    )
    evidence = tuple(sorted(reference) + sorted(external - reference))[:5]
    return make_signal(
        "citations_links",
        "Sources and internal links",
        score,
        basis="heuristic",
        found=(
            f"{len(external)} outside site(s) linked ({len(reference)} reference-style), "
            f"{len(internal)} internal page(s), {len(descriptive)}/{len(content)} links with "
            "descriptive text."
        ),
        evidence=evidence,
        why=(
            "Linking to the sources behind a claim lets a reader verify it, and linking related "
            "pages shows how an answer fits into the rest of the site. 'Reference-style' means "
            "government, university, DOI or arXiv hosts, a rough stand-in for primary sources."
        ),
        fix=(
            "Link the primary sources behind your key claims, link related pages on your own "
            "site, and write anchor text that says what the target is ('cold brew storage "
            "guide', not 'click here')."
        ),
    )
