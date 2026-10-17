"""Can answer-engine crawlers reach the page, and is there text for them to read?"""

from __future__ import annotations

from aeo_audit.agents import AGENTS, COUNTED_ROLES
from aeo_audit.model import Signal
from aeo_audit.signals.context import Context, make_signal


def blocked_agents(ctx: Context) -> list[str]:
    """Tokens of every known AI crawler that robots.txt forbids from this page."""
    if ctx.robots is None:
        return []
    return [a.token for a in AGENTS if not ctx.robots.allows(a.token, ctx.page.url)]


def crawl_access(ctx: Context) -> Signal:
    label = "Crawler access (robots.txt)"
    why = (
        "A crawler that is not allowed to fetch a page cannot quote it. robots.txt is the "
        "control that AI vendors document for their crawlers."
    )
    if ctx.robots is None:
        if ctx.robots_status == "missing":
            return make_signal(
                "crawl_access",
                label,
                100,
                basis="mechanical",
                why=why,
                fix="",
                found="No robots.txt, so no crawler is forbidden from the page.",
            )
        return make_signal(
            "crawl_access",
            label,
            20,
            basis="mechanical",
            why=why,
            found="robots.txt could not be fetched (server error or timeout).",
            fix=(
                "Make /robots.txt answer 200 (or 404 if you have no rules). RFC 9309 tells "
                "compliant crawlers to treat an unreachable robots.txt as 'disallow everything'."
            ),
        )

    counted = [a for a in AGENTS if a.role in COUNTED_ROLES]
    blocked = set(blocked_agents(ctx))
    blocked_counted = [a for a in counted if a.token in blocked]
    shown = [a for a in AGENTS if a.token in blocked or a.role in COUNTED_ROLES]
    shown.sort(key=lambda a: a.token not in blocked)  # blocked first, stable otherwise
    evidence = tuple(
        f"{a.token} ({a.operator}, {a.role}): {'blocked' if a.token in blocked else 'allowed'}"
        for a in shown
    )
    score = 100 * (len(counted) - len(blocked_counted)) / len(counted)
    training_blocked = sorted(t for t in blocked if t not in {a.token for a in blocked_counted})
    if blocked_counted:
        found = "Blocked from this page: " + ", ".join(a.token for a in blocked_counted) + "."
    else:
        found = "Every search and user-triggered AI crawler may fetch this page."
    if training_blocked:
        found += f" Training crawlers blocked (not penalised): {', '.join(training_blocked)}."
    tokens = ", ".join(a.token for a in blocked_counted)
    return make_signal(
        "crawl_access",
        label,
        score,
        basis="mechanical",
        why=why,
        found=found,
        evidence=evidence,
        always_fix=bool(blocked_counted),
        fix=(
            f"Remove or narrow the Disallow rules that match this page for {tokens}. "
            "If blocking them is a deliberate policy, this signal is working as intended."
        ),
    )


def renderability(ctx: Context) -> Signal:
    page = ctx.page
    words = page.word_count
    score = min(100.0, words / 300 * 100)
    notes = []
    if "javascript" in page.noscript_text.lower() and words < 150:
        score = min(score, 20)
        notes.append("the page asks for JavaScript")
    if page.root_shell and words < 100:
        score = min(score, 10)
        notes.append("an empty app shell")
    found = f"{words} words of readable text in the HTML, {page.script_count} scripts"
    if notes:
        found += f" ({', '.join(notes)})"
    return make_signal(
        "renderability",
        "Text present without JavaScript",
        score,
        basis="heuristic",
        found=found,
        why=(
            "This audit reads the HTML exactly as served. A page whose text only appears after "
            "scripts run may look empty to any crawler that does not execute JavaScript, and "
            "vendors do not all document whether theirs does."
        ),
        fix=(
            "Serve the main content in the initial HTML (server-side rendering or static "
            "generation) so it is readable without running scripts."
        ),
    )
