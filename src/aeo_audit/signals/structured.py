"""JSON-LD structured data: which schema.org types, how complete, and honest about the page."""

from __future__ import annotations

import re
from typing import Any

from aeo_audit.model import Signal
from aeo_audit.page import declared_types
from aeo_audit.signals.context import Context, make_signal

# Credit for having a type at all, before completeness is applied. Answer-shaped
# types come first because they describe content a reader would quote; entity
# types say who or what the page is about; context types only place the page.
ANSWER_TYPES = frozenset(
    {"faqpage", "howto", "qapage", "article", "blogposting", "newsarticle", "techarticle"}
)
ENTITY_TYPES = frozenset(
    {"organization", "person", "localbusiness", "product", "softwareapplication", "recipe", "event"}
)
CONTEXT_TYPES = frozenset({"breadcrumblist", "website", "webpage"})

_ARTICLE = ("headline", "author", "datePublished")
EXPECTED: dict[str, tuple[str, ...]] = {
    "article": _ARTICLE,
    "blogposting": _ARTICLE,
    "newsarticle": _ARTICLE,
    "techarticle": _ARTICLE,
    "howto": ("name", "step"),
    "qapage": ("mainEntity",),
    "localbusiness": ("name", "address"),
    "breadcrumblist": ("itemListElement",),
}
_TIER = {**dict.fromkeys(ANSWER_TYPES, 30), **dict.fromkeys(ENTITY_TYPES, 20)}
_TIER.update(dict.fromkeys(CONTEXT_TYPES, 8))


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _faq_credit(node: dict[str, Any], visible: str) -> tuple[float, str]:
    """Share of the FAQ's questions that are complete and also appear on the page."""
    raw = node.get("mainEntity")
    questions = [q for q in (raw if isinstance(raw, list) else [raw]) if isinstance(q, dict)]
    if not questions:
        return 0.0, "FAQPage has no Question entries in mainEntity"
    complete = matched = 0
    for question in questions:
        name = question.get("name")
        answer = question.get("acceptedAnswer")
        text = answer.get("text") if isinstance(answer, dict) else None
        if isinstance(name, str) and name.strip() and isinstance(text, str) and text.strip():
            complete += 1
            if _norm(name) in visible:
                matched += 1
    total = len(questions)
    detail = (
        f"FAQPage: {complete}/{total} questions have an answer, "
        f"{matched}/{total} appear on the page"
    )
    return (complete / total) * (matched / total if total else 0), detail


def structured_data(ctx: Context) -> Signal:
    page = ctx.page
    visible = _norm(page.text)
    best: dict[str, tuple[float, str]] = {}
    for node in page.nodes():
        for shown in declared_types(node):
            name = shown.lower()
            tier = _TIER.get(name)
            if tier is None:
                continue
            if name == "faqpage":
                completeness, detail = _faq_credit(node, visible)
            else:
                expected = EXPECTED.get(name, ("name",))
                have = [p for p in expected if _present(node.get(p))]
                completeness = len(have) / len(expected)
                missing = [p for p in expected if p not in have]
                detail = f"{shown}: " + (
                    "complete" if not missing else "missing " + ", ".join(missing)
                )
            credit = tier * completeness
            if name not in best or credit > best[name][0]:
                best[name] = (credit, detail)

    evidence = [detail for _, detail in best.values()]
    if page.jsonld_errors:
        evidence.append(f"{page.jsonld_errors} JSON-LD block(s) could not be parsed")
    score = sum(credit for credit, _ in best.values())
    if not best:
        found = "No usable JSON-LD structured data."
    else:
        found = f"{len(best)} schema.org type(s): " + ", ".join(sorted(best))
    return make_signal(
        "structured_data",
        "Structured data (JSON-LD)",
        score,
        basis="heuristic",
        found=found,
        evidence=tuple(evidence),
        why=(
            "Structured data states what a page is in a machine-readable form. Search engines "
            "document using it; whether answer engines weigh it is not established, so treat "
            "this as hygiene rather than a proven ranking factor."
        ),
        fix=(
            "Add JSON-LD that matches what is visible: Article (headline, author, datePublished) "
            "for posts, FAQPage when the page really has Q&A, Organization or Person for the "
            "publisher. Markup that describes content the page does not show can hurt you."
        ),
    )
