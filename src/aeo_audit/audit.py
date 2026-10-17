"""Run every signal over one page and combine the results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from aeo_audit import robots
from aeo_audit.fetch import FetchError, Resolver, fetch, system_resolver
from aeo_audit.model import Audit, Grade, Recommendation
from aeo_audit.page import parse_page
from aeo_audit.signals import SIGNALS, Context, blocked_agents

RobotsStatus = Literal["found", "missing", "unavailable"]
_GRADES: tuple[tuple[int, Grade], ...] = ((90, "A"), (75, "B"), (60, "C"), (45, "D"))


def grade_for(score: int) -> Grade:
    return next((grade for floor, grade in _GRADES if score >= floor), "F")


def audit_html(
    html: str,
    url: str,
    *,
    robots_text: str | None = None,
    robots_status: RobotsStatus | None = None,
    now: datetime | None = None,
    notes: tuple[str, ...] = (),
) -> Audit:
    """Audit already-fetched HTML. Pure: the same inputs always give the same result.

    Pass `robots_text` when robots.txt was found; otherwise say why with
    `robots_status` ("missing" when the server had none, "unavailable" when it
    could not be read). With neither, the page is treated as having no robots.txt.
    """
    moment = now or datetime.now(UTC)
    status: RobotsStatus = robots_status or ("found" if robots_text is not None else "missing")
    context = Context(
        page=parse_page(html, url),
        robots=robots.parse(robots_text) if robots_text is not None else None,
        robots_status=status,
        now=moment,
    )
    signals = tuple(signal(context) for signal in SIGNALS)
    score = round(sum(s.score * s.weight / 100 for s in signals))
    # Plain facts (a blocked crawler) come before rules of thumb, then by points available.
    ordered = sorted(
        signals, key=lambda s: (s.basis != "mechanical", -(s.weight * (100 - s.score)))
    )
    fixes = [
        Recommendation(s.id, s.fix, round(s.weight * (100 - s.score) / 100))
        for s in ordered
        if s.fix is not None
    ]
    return Audit(
        url=url,
        audited_at=moment,
        score=score,
        grade=grade_for(score),
        signals=signals,
        recommendations=tuple(fixes),
        blocked_agents=tuple(blocked_agents(context)),
        notes=notes,
    )


def audit_url(
    url: str,
    *,
    timeout: float = 10.0,
    allow_private: bool = False,
    resolver: Resolver = system_resolver,
    now: datetime | None = None,
) -> Audit:
    """Fetch the page and its robots.txt (every hop SSRF-checked) and audit them."""
    normalized = url.strip()
    if "://" not in normalized:
        normalized = f"https://{normalized}"
    page = fetch(normalized, timeout=timeout, allow_private=allow_private, resolver=resolver)
    if "html" not in page.content_type.lower() and "xml" not in page.content_type.lower():
        raise FetchError(f"Expected an HTML page, got {page.content_type or 'unknown content'}.")
    notes: list[str] = []
    if page.redirects:
        notes.append(f"Followed {len(page.redirects)} redirect(s) to {page.url}.")
    if page.truncated:
        notes.append("The page was larger than the 2 MB limit and was cut off.")

    parts = urlsplit(page.url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    robots_text: str | None = None
    status: RobotsStatus = "found"
    try:
        reply = fetch(
            robots_url,
            timeout=timeout,
            max_bytes=500_000,
            allow_private=allow_private,
            resolver=resolver,
        )
        robots_text = reply.text()
    except FetchError as error:
        # RFC 9309: a 4xx means "no robots.txt"; anything else is an unreadable one.
        client_error = error.status is not None and 400 <= error.status < 500
        status = "missing" if client_error else "unavailable"
        if status == "unavailable":
            notes.append(f"robots.txt could not be read: {error}")
    return audit_html(
        page.text(),
        page.url,
        robots_text=robots_text,
        robots_status=status,
        now=now,
        notes=tuple(notes),
    )
