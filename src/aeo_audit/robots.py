"""A robots.txt matcher that follows RFC 9309 (the Robots Exclusion Protocol).

Python's `urllib.robotparser` predates the RFC: it has no `*` or `$` wildcards
in paths and picks the first matching rule rather than the longest. Both matter
for deciding whether an AI crawler may fetch a page, so this module implements
the RFC's rules directly: group selection by product token, longest match wins,
and `Allow` wins a tie.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit


@dataclass(slots=True)
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, path pattern)


@dataclass(frozen=True, slots=True)
class RobotsTxt:
    groups: tuple[Group, ...]

    def rules_for(self, agent: str) -> list[tuple[bool, str]]:
        """Rules of every group naming `agent`, else those of the `*` groups."""
        token = agent.lower()
        named = [r for g in self.groups if token in g.agents for r in g.rules]
        if any(token in g.agents for g in self.groups):
            return named
        return [r for g in self.groups if "*" in g.agents for r in g.rules]

    def allows(self, agent: str, url_or_path: str) -> bool:
        """Whether `agent` may fetch the URL's path and query."""
        target = _path_and_query(url_or_path)
        best: tuple[int, bool] | None = None
        for allow, pattern in self.rules_for(agent):
            if not pattern:
                continue  # an empty Disallow means "allow everything"
            if _compile(pattern).match(target) is None:
                continue
            candidate = (len(pattern), allow)
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and allow):
                best = candidate
        return True if best is None else best[1]

    def names(self, agent: str) -> bool:
        """Whether some group addresses `agent` by name rather than through `*`."""
        return any(agent.lower() in g.agents for g in self.groups)


def parse(text: str) -> RobotsTxt:
    """Parse robots.txt. Unknown lines are ignored, as the RFC requires."""
    groups: list[Group] = []
    current: Group | None = None
    collecting_agents = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or not collecting_agents:
                current = Group()
                groups.append(current)
            current.agents.append(value.lower())
            collecting_agents = True
        elif key in ("allow", "disallow"):
            collecting_agents = False
            if current is not None:
                current.rules.append((key == "allow", value))
    return RobotsTxt(tuple(groups))


def _path_and_query(url_or_path: str) -> str:
    parts = urlsplit(url_or_path)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(piece) for piece in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))
