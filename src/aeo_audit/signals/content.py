"""What the text says: question-and-answer structure and concrete, checkable detail."""

from __future__ import annotations

import re

from aeo_audit.model import Signal
from aeo_audit.signals.context import Context, make_signal

_ANSWER_WORDS = range(15, 121)

_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
_UNITS = (
    r"mg|g|kg|lbs?|oz|ml|l|cm|mm|m|km|mi|ft|in|°[CF]|degrees|seconds?|minutes?|mins?|hours?|hrs?"
    r"|days?|weeks?|months?|years?"
)
_DETAIL = re.compile(
    "|".join(
        [
            r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|million|billion))?",  # money
            r"\b\d+(?:\.\d+)?\s?%",  # percentages
            rf"\b\d+(?:[.,]\d+)?(?:\s?[-–]\s?\d+(?:[.,]\d+)?)?\s?(?:{_UNITS})\b",  # measures
            rf"\b(?:{_MONTHS})[a-z]*\.?\s+\d{{1,2}}(?:,?\s+(?:19|20)\d{{2}})?",  # dates
            r"\b(?:19|20)\d{2}\b",  # years
            r"\b(?:according to|sources?:|studies|study|survey|reported by|research(?:ers)?"
            r"|published in|per the)\b",  # attribution
        ]
    ),
    re.IGNORECASE,
)


def _is_question(text: str) -> bool:
    """A heading counts only if it actually ends in a question mark: false positives hurt more."""
    return text.rstrip().endswith("?") and 2 <= len(text.split()) <= 25


def question_structure(ctx: Context) -> Signal:
    blocks = ctx.page.blocks
    questions: list[str] = []
    ready = 0
    for index, block in enumerate(blocks):
        if block.kind != "heading" or not 2 <= block.level <= 4 or not _is_question(block.text):
            continue
        questions.append(block.text)
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        if following is not None and following.kind == "text" and following.words in _ANSWER_WORDS:
            ready += 1
    score = 20 * ready + 6 * (len(questions) - ready)
    if not questions:
        found = "No headings phrased as questions."
    else:
        found = (
            f"{len(questions)} question heading(s), {ready} followed directly by a short answer."
        )
    return make_signal(
        "question_structure",
        "Question-and-answer structure",
        score,
        basis="heuristic",
        found=found,
        evidence=tuple(questions[:5]),
        why=(
            "A heading that asks a question, followed at once by a self-contained answer of a "
            "few sentences, is easy to lift out and quote without surrounding context."
        ),
        fix=(
            "Turn the questions your readers actually ask into H2/H3 headings and put a direct "
            "answer of 15 to 120 words in the paragraph immediately after each one."
        ),
    )


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def specificity(ctx: Context) -> Signal:
    page = ctx.page
    words = page.word_count
    why = (
        "Numbers, dates, units and named sources are the parts of a page that can be checked, "
        "and vague prose gives a reader or a model little to quote. Measured here as detail "
        "per 1,000 words; it is a crude proxy and cannot tell true details from false ones."
    )
    fix = (
        "Replace adjectives with figures and name where they come from: instead of 'lasts a "
        "while', write 'keeps 7 to 10 days refrigerated', and say who measured it."
    )
    if words < 50:
        return make_signal(
            "specificity",
            "Concrete, citable detail",
            0,
            basis="heuristic",
            found=f"Only {words} words of text, too little to judge.",
            why=why,
            fix=fix,
        )
    text = page.text
    spans = _merge([m.span() for m in _DETAIL.finditer(text)])
    density = len(spans) / words * 1000
    snippets = tuple(dict.fromkeys(text[a:b].strip() for a, b in spans))[:5]
    return make_signal(
        "specificity",
        "Concrete, citable detail",
        density / 25 * 100,
        basis="heuristic",
        found=f"{len(spans)} concrete details in {words} words ({density:.0f} per 1,000).",
        evidence=snippets,
        why=why,
        fix=fix,
    )
