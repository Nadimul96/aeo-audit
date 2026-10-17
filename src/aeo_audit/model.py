"""Result types shared by the signals, the audit, the report and the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Basis = Literal["mechanical", "heuristic"]
Grade = Literal["A", "B", "C", "D", "F"]


@dataclass(frozen=True, slots=True)
class Signal:
    """One thing that was checked, how it scored, and what to do about it.

    `basis` says how much weight the score can bear. "mechanical" means the page
    plainly does or does not do something (robots.txt blocks a crawler, a date
    is present). "heuristic" means a rule of thumb about what is likely to help
    a page be quoted; nobody has measured that effect, including this tool.
    """

    id: str
    label: str
    weight: int
    score: int
    basis: Basis
    found: str
    evidence: tuple[str, ...]
    why: str
    fix: str | None


@dataclass(frozen=True, slots=True)
class Recommendation:
    signal_id: str
    fix: str
    points: int


@dataclass(frozen=True, slots=True)
class Audit:
    url: str
    audited_at: datetime
    score: int
    grade: Grade
    signals: tuple[Signal, ...]
    recommendations: tuple[Recommendation, ...]
    blocked_agents: tuple[str, ...]
    notes: tuple[str, ...]
