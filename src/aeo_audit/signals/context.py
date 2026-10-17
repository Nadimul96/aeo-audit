"""What every signal receives, and the one place that builds a `Signal`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from aeo_audit.model import Basis, Signal
from aeo_audit.page import Page
from aeo_audit.robots import RobotsTxt

# Must sum to 100 (a test enforces it). The weights are judgment calls, not
# measurements: they say how much I think each thing matters relative to the
# others, and nothing here has been validated against real citation data.
WEIGHTS: dict[str, int] = {
    "crawl_access": 15,
    "structured_data": 20,
    "question_structure": 15,
    "specificity": 12,
    "authorship_freshness": 12,
    "document_structure": 10,
    "citations_links": 8,
    "renderability": 8,
}

# A fix is only suggested below this score.
FIX_BELOW = 70


@dataclass(frozen=True, slots=True)
class Context:
    page: Page
    robots: RobotsTxt | None
    robots_status: Literal["found", "missing", "unavailable"]
    now: datetime


def make_signal(
    signal_id: str,
    label: str,
    score: float,
    *,
    basis: Basis,
    found: str,
    why: str,
    fix: str,
    evidence: tuple[str, ...] = (),
    always_fix: bool = False,
) -> Signal:
    """Clamp the score to 0-100; attach the fix when the score or `always_fix` calls for one."""
    value = max(0, min(100, round(score)))
    return Signal(
        id=signal_id,
        label=label,
        weight=WEIGHTS[signal_id],
        score=value,
        basis=basis,
        found=found,
        evidence=evidence[:12],
        why=why,
        fix=fix if value < FIX_BELOW or always_fix else None,
    )
