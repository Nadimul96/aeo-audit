"""RFC 9309 behaviour that urllib.robotparser gets wrong or does not support."""

from __future__ import annotations

import pytest

from aeo_audit.robots import parse


def allows(text: str, agent: str, path: str) -> bool:
    return parse(text).allows(agent, path)


def test_no_rules_means_allowed() -> None:
    assert allows("", "GPTBot", "/anything")
    assert allows("User-agent: *\nDisallow:\n", "GPTBot", "/anything")


def test_specific_group_overrides_the_wildcard_group() -> None:
    text = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n"
    assert allows(text, "GPTBot", "/page")
    assert not allows(text, "ClaudeBot", "/page")


def test_a_named_group_does_not_inherit_wildcard_rules() -> None:
    text = "User-agent: *\nDisallow: /private/\n\nUser-agent: GPTBot\nDisallow: /secret/\n"
    assert allows(text, "GPTBot", "/private/x")
    assert not allows(text, "GPTBot", "/secret/x")


def test_consecutive_user_agent_lines_share_one_group() -> None:
    text = "User-agent: OAI-SearchBot\nUser-agent: PerplexityBot\nDisallow: /\n"
    assert not allows(text, "OAI-SearchBot", "/")
    assert not allows(text, "PerplexityBot", "/")
    assert allows(text, "Claude-User", "/")


def test_repeated_groups_for_one_agent_are_combined() -> None:
    text = "User-agent: GPTBot\nDisallow: /a/\n\nUser-agent: GPTBot\nDisallow: /b/\n"
    assert not allows(text, "GPTBot", "/a/1")
    assert not allows(text, "GPTBot", "/b/1")


def test_the_longest_matching_rule_wins() -> None:
    text = "User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n"
    assert not allows(text, "GPTBot", "/docs/internal")
    assert allows(text, "GPTBot", "/docs/public/guide")


def test_allow_wins_a_tie_in_length() -> None:
    text = "User-agent: *\nDisallow: /page\nAllow: /page\n"
    assert allows(text, "GPTBot", "/page")


def test_rule_order_does_not_matter() -> None:
    first = "User-agent: *\nAllow: /docs/public/\nDisallow: /docs/\n"
    second = "User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n"
    for text in (first, second):
        assert allows(text, "GPTBot", "/docs/public/x")
        assert not allows(text, "GPTBot", "/docs/x")


@pytest.mark.parametrize(
    ("pattern", "path", "blocked"),
    [
        ("/*.pdf", "/files/report.pdf", True),
        ("/*.pdf", "/files/report.pdf.html", True),
        ("/*.pdf$", "/files/report.pdf", True),
        ("/*.pdf$", "/files/report.pdf.html", False),
        ("/private*/", "/private-area/x", True),
        ("/*?session=", "/page?session=1", True),
        ("/*?session=", "/page", False),
        ("/", "/anything", True),
    ],
)
def test_wildcards_and_end_anchor(pattern: str, path: str, blocked: bool) -> None:
    assert allows(f"User-agent: *\nDisallow: {pattern}\n", "GPTBot", path) is not blocked


def test_the_query_string_is_part_of_the_match() -> None:
    text = "User-agent: *\nDisallow: /search?q=\n"
    assert not allows(text, "GPTBot", "https://site.example/search?q=coffee")
    assert allows(text, "GPTBot", "https://site.example/search")


def test_paths_are_case_sensitive_and_agents_are_not() -> None:
    text = "User-agent: gptbot\nDisallow: /Private/\n"
    assert not allows(text, "GPTBot", "/Private/x")
    assert allows(text, "GPTBot", "/private/x")


def test_comments_blank_lines_and_unknown_fields_are_ignored() -> None:
    text = (
        "# policy\nUser-agent: GPTBot # the crawler\nCrawl-delay: 10\n\nDisallow: /x # no\n"
        "Sitemap: https://site.example/sitemap.xml\n"
    )
    assert not allows(text, "GPTBot", "/x")
    assert allows(text, "GPTBot", "/y")


def test_rules_before_any_user_agent_are_ignored() -> None:
    assert allows("Disallow: /\n", "GPTBot", "/")


def test_names_reports_whether_an_agent_is_addressed_directly() -> None:
    robots = parse("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n")
    assert robots.names("gptbot")
    assert not robots.names("ClaudeBot")
