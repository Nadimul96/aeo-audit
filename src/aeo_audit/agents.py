"""The AI crawlers and fetchers whose access `crawl_access` checks.

This is data, and it goes stale: vendors add and rename user-agent tokens. The
names below are the ones the operators document for their crawlers as of
October 2026; check each vendor's crawler page before relying on the list.

`role` matters for scoring. Blocking a "training" crawler is a legitimate
policy choice that does not stop a page from appearing in a live answer, so
only "search" and "user" roles count against a page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["search", "user", "training"]


@dataclass(frozen=True, slots=True)
class Agent:
    token: str
    operator: str
    role: Role


AGENTS: tuple[Agent, ...] = (
    Agent("OAI-SearchBot", "OpenAI", "search"),
    Agent("ChatGPT-User", "OpenAI", "user"),
    Agent("GPTBot", "OpenAI", "training"),
    Agent("Claude-SearchBot", "Anthropic", "search"),
    Agent("Claude-User", "Anthropic", "user"),
    Agent("ClaudeBot", "Anthropic", "training"),
    Agent("PerplexityBot", "Perplexity", "search"),
    Agent("Perplexity-User", "Perplexity", "user"),
    Agent("Googlebot", "Google", "search"),
    Agent("Google-Extended", "Google", "training"),
    Agent("Applebot-Extended", "Apple", "training"),
    Agent("CCBot", "Common Crawl", "training"),
)

COUNTED_ROLES = frozenset({"search", "user"})
