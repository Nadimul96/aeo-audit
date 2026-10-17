"""Whether the document is built so that a section can be found, bounded and quoted."""

from __future__ import annotations

from aeo_audit.model import Signal
from aeo_audit.signals.context import Context, make_signal


def _skipped_levels(levels: list[int]) -> int:
    previous, skips = 0, 0
    for level in levels:
        if level > previous + 1:
            skips += 1
        previous = level
    return skips


def document_structure(ctx: Context) -> Signal:
    page = ctx.page
    levels = [h.level for h in page.headings()]
    h1 = levels.count(1)
    h2 = levels.count(2)
    skips = _skipped_levels(levels)
    description = page.meta.get("description", "")
    title = page.title

    points = 0
    problems: list[str] = []
    if h1 == 1:
        points += 25
    elif h1 > 1:
        points += 8
        problems.append(f"{h1} H1 headings")
    else:
        problems.append("no H1")
    if levels and not skips:
        points += 15
    elif skips:
        problems.append(f"{skips} skipped heading level(s)")
    points += 15 if h2 >= 3 else 7 if h2 >= 1 else 0
    points += 10 if "main" in page.landmarks else 0
    points += 5 if "article" in page.landmarks else 0
    points += 5 if page.lang else 0
    points += 10 if 10 <= len(title) <= 70 else 5 if title else 0
    points += 10 if 50 <= len(description) <= 180 else 5 if description else 0
    points += 5 if page.canonical else 0
    if not page.lang:
        problems.append("no lang attribute")
    if not title:
        problems.append("no title")
    if not description:
        problems.append("no meta description")

    summary = f"H1 x{h1}, H2 x{h2}; <main> {'yes' if 'main' in page.landmarks else 'no'}"
    return make_signal(
        "document_structure",
        "Document structure",
        points,
        basis="heuristic",
        found=summary + (f"; {'; '.join(problems)}" if problems else "") + ".",
        evidence=tuple(h.text for h in page.headings() if h.level <= 2)[:5],
        why=(
            "One H1, headings that nest without gaps and landmark elements mark where each "
            "section starts and ends, so a passage can be taken out with its heading intact."
        ),
        fix=(
            "Use exactly one H1, nest headings without skipping levels, wrap the content in "
            "<main> (and posts in <article>), and set a lang attribute, a 10-70 character "
            "title, a 50-180 character meta description and a canonical link."
        ),
    )
