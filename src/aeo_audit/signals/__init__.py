"""The eight signals, in report order."""

from __future__ import annotations

from collections.abc import Callable

from aeo_audit.model import Signal
from aeo_audit.signals.access import blocked_agents, crawl_access, renderability
from aeo_audit.signals.content import question_structure, specificity
from aeo_audit.signals.context import WEIGHTS, Context
from aeo_audit.signals.document import document_structure
from aeo_audit.signals.structured import structured_data
from aeo_audit.signals.trust import authorship_freshness, citations_links

SIGNALS: tuple[Callable[[Context], Signal], ...] = (
    crawl_access,
    structured_data,
    question_structure,
    specificity,
    authorship_freshness,
    document_structure,
    citations_links,
    renderability,
)

__all__ = ["SIGNALS", "WEIGHTS", "Context", "blocked_agents"]
