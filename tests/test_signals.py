from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aeo_audit import audit_html, grade_for
from aeo_audit.model import Audit
from aeo_audit.signals import SIGNALS, WEIGHTS
from conftest import GOOD_URL, NOW, THIN_URL, fixture_text


def run(html: str, url: str = "https://site.example/post", **kwargs: object) -> Audit:
    return audit_html(html, url, now=NOW, **kwargs)  # type: ignore[arg-type]


def signal(audit: Audit, signal_id: str):  # type: ignore[no-untyped-def]
    return next(s for s in audit.signals if s.id == signal_id)


def test_weights_sum_to_one_hundred_and_every_signal_has_one() -> None:
    assert sum(WEIGHTS.values()) == 100
    assert len(SIGNALS) == len(WEIGHTS)


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (100, "A"),
        (90, "A"),
        (89, "B"),
        (75, "B"),
        (74, "C"),
        (60, "C"),
        (59, "D"),
        (45, "D"),
        (44, "F"),
        (0, "F"),
    ],
)
def test_grade_boundaries(score: int, grade: str) -> None:
    assert grade_for(score) == grade


# --- crawl access -----------------------------------------------------------


def test_no_robots_txt_means_no_crawler_is_blocked() -> None:
    audit = run("<p>x</p>", robots_status="missing")
    assert signal(audit, "crawl_access").score == 100
    assert audit.blocked_agents == ()


def test_an_unreachable_robots_txt_scores_low_with_an_explanation() -> None:
    access = signal(run("<p>x</p>", robots_status="unavailable"), "crawl_access")
    assert access.score == 20
    assert access.fix and "RFC 9309" in access.fix


def test_blocking_search_crawlers_costs_points_and_always_shows_a_fix() -> None:
    robots = "User-agent: OAI-SearchBot\nUser-agent: PerplexityBot\nDisallow: /\n"
    audit = run("<p>x</p>", robots_text=robots)
    access = signal(audit, "crawl_access")
    assert access.score == 71  # 2 of 7 counted agents blocked
    assert access.fix is not None, "a block must be surfaced even when the score is above 70"
    assert set(audit.blocked_agents) == {"OAI-SearchBot", "PerplexityBot"}
    assert access.evidence[0].endswith("blocked")


def test_blocking_only_training_crawlers_is_not_penalised() -> None:
    robots = "User-agent: GPTBot\nUser-agent: ClaudeBot\nUser-agent: CCBot\nDisallow: /\n"
    audit = run("<p>x</p>", robots_text=robots)
    access = signal(audit, "crawl_access")
    assert access.score == 100
    assert access.fix is None
    assert "GPTBot" in access.found
    assert "GPTBot" in audit.blocked_agents


def test_a_path_specific_rule_only_matters_for_the_audited_page() -> None:
    robots = "User-agent: *\nDisallow: /members/\n"
    assert run("<p>x</p>", "https://s.example/blog/a", robots_text=robots).blocked_agents == ()
    assert (
        len(run("<p>x</p>", "https://s.example/members/a", robots_text=robots).blocked_agents) == 12
    )


# --- structured data ----------------------------------------------------------


def ld(payload: str) -> str:
    return f'<script type="application/ld+json">{payload}</script><main><p>text</p></main>'


def test_no_json_ld_scores_zero() -> None:
    assert signal(run("<p>x</p>"), "structured_data").score == 0


def test_a_complete_article_earns_its_full_tier_and_an_incomplete_one_less() -> None:
    full = ld('{"@type":"Article","headline":"h","author":"a","datePublished":"2026-01-01"}')
    partial = ld('{"@type":"Article","headline":"h"}')
    assert signal(run(full), "structured_data").score == 30
    assert signal(run(partial), "structured_data").score == 10


def test_faq_markup_must_match_what_the_page_shows() -> None:
    faq = (
        '{"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Is it hidden?",'
        '"acceptedAnswer":{"@type":"Answer","text":"Yes."}}]}'
    )
    hidden = signal(run(ld(faq)), "structured_data")
    shown = signal(
        run(ld(faq).replace("<p>text</p>", "<h2>Is it hidden?</h2><p>Yes.</p>")), "structured_data"
    )
    assert hidden.score == 0
    assert shown.score == 30
    assert "0/1 appear on the page" in hidden.evidence[0]


def test_malformed_json_ld_is_reported_not_fatal() -> None:
    result = signal(run(ld("{ nope")), "structured_data")
    assert result.score == 0
    assert any("could not be parsed" in e for e in result.evidence)


def test_unknown_types_earn_nothing_and_the_score_is_capped() -> None:
    assert signal(run(ld('{"@type":"Thing","name":"x"}')), "structured_data").score == 0
    many = ",".join(
        f'{{"@type":"{t}","name":"n","headline":"h","author":"a","datePublished":"d"}}'
        for t in ("Article", "BlogPosting", "NewsArticle", "Organization", "Person", "Product")
    )
    assert signal(run(ld(f"[{many}]")), "structured_data").score == 100


# --- question structure ------------------------------------------------------


def test_a_question_heading_needs_a_question_mark_and_a_nearby_answer() -> None:
    answer = " ".join(["word"] * 30)
    ready = signal(run(f"<h2>Why does it work?</h2><p>{answer}</p>"), "question_structure")
    no_answer = signal(run("<h2>Why does it work?</h2><h2>Next</h2>"), "question_structure")
    no_mark = signal(run(f"<h2>Why it works</h2><p>{answer}</p>"), "question_structure")
    assert (ready.score, no_answer.score, no_mark.score) == (20, 6, 0)


def test_answers_that_are_too_short_or_too_long_do_not_count() -> None:
    short = signal(run("<h2>Why is it so?</h2><p>Because.</p>"), "question_structure")
    long = signal(run("<h2>Why is it so?</h2><p>" + "word " * 200 + "</p>"), "question_structure")
    assert short.score == long.score == 6


# --- specificity ----------------------------------------------------------------


def test_too_little_text_cannot_be_judged() -> None:
    assert signal(run("<p>$5 and 10%</p>"), "specificity").score == 0


def test_detail_is_measured_per_thousand_words_not_in_total() -> None:
    detail = "It costs $12.50 and lasts 14 days. According to a 2024 survey, 82% agree. "
    dense = signal(run(f"<p>{detail * 4}</p>"), "specificity")
    diluted = signal(run(f"<p>{detail * 4}{'filler ' * 8000}</p>"), "specificity")
    assert dense.score == 100
    assert diluted.score < 20
    assert "$12.50" in dense.evidence


def test_overlapping_matches_count_once() -> None:
    padding = "plain words " * 30
    one = signal(run(f"<p>{padding} on March 3, 2024 {padding}</p>"), "specificity")
    assert "1 concrete details" in one.found


# --- authorship and freshness -----------------------------------------------


def test_dates_make_a_page_fresh_and_age_makes_it_stale() -> None:
    def with_date(value: str) -> int:
        html = (
            '<meta name="author" content="A B">'
            f'<meta property="article:published_time" content="{value}"><p>x</p>'
        )
        return signal(run(html), "authorship_freshness").score

    assert with_date("2026-08-01") == 35 + 20 + 20
    assert with_date("2025-03-01") == 35 + 20 + 10
    assert with_date("2019-01-01") == 35 + 20


def test_future_dates_do_not_count_as_fresh() -> None:
    html = '<meta property="article:published_time" content="2030-01-01"><p>x</p>'
    assert signal(run(html), "authorship_freshness").score == 20


def test_a_byline_in_the_text_is_credited_separately_from_metadata() -> None:
    assert signal(run("<p>By Maya Okafor</p>"), "authorship_freshness").score == 15
    assert signal(run("<p>by somebody</p>"), "authorship_freshness").score == 0


def test_json_ld_authors_are_found_in_nested_nodes() -> None:
    html = ld(
        '{"@type":"Article","author":[{"@type":"Person","name":"Ana","url":"https://a.example"}]}'
    )
    result = signal(run(html), "authorship_freshness")
    assert result.score == 35 + 10


# --- document structure -------------------------------------------------------


def test_one_h1_and_nested_headings_beat_a_flat_or_skipped_outline() -> None:
    good = "<h1>A</h1><h2>B</h2><h3>C</h3>"
    skipped = "<h1>A</h1><h3>C</h3>"
    two_h1 = "<h1>A</h1><h1>B</h1>"
    scores = [signal(run(h), "document_structure").score for h in (good, skipped, two_h1)]
    assert scores[0] > scores[1] > scores[2]


# --- links ---------------------------------------------------------------------


def test_reference_hosts_and_descriptive_anchors_score_higher() -> None:
    links = (
        '<main><a href="https://www.cdc.gov/x">CDC guidance</a>'
        '<a href="https://nih.gov/y">NIH review</a>'
        '<a href="https://blog.example/z">a blog</a>'
        '<a href="/a">our guide</a><a href="/b">click here</a>'
        '<a href="https://twitter.com/me">me</a></main>'
    )
    result = signal(run(links), "citations_links")
    assert "3 outside site(s) linked (2 reference-style)" in result.found
    assert "2 internal page(s)" in result.found
    assert result.evidence[:2] == ("cdc.gov", "nih.gov")


def test_a_pages_own_host_and_nofollow_links_are_not_citations() -> None:
    html = '<main><a href="https://site.example/a">own</a><a rel="nofollow" href="https://x.org">ad</a></main>'
    assert "0 outside" in signal(run(html), "citations_links").found


# --- renderability --------------------------------------------------------------


def test_an_empty_app_shell_scores_very_low() -> None:
    html = '<div id="root"></div><noscript>Enable JavaScript to run this app.</noscript>'
    assert signal(run(html), "renderability").score == 0


# --- whole pages ------------------------------------------------------------------


def test_the_good_fixture_is_an_a_and_the_thin_one_an_f() -> None:
    robots = fixture_text("robots-open.txt")
    good = audit_html(fixture_text("well-structured.html"), GOOD_URL, robots_text=robots, now=NOW)
    thin = audit_html(fixture_text("thin.html"), THIN_URL, robots_text=robots, now=NOW)
    assert (good.grade, thin.grade) == ("A", "F")
    assert good.score >= 90 and thin.score <= 30


def test_recommendations_put_plain_facts_first_then_points() -> None:
    robots = fixture_text("robots-blocking.txt")
    audit = audit_html(fixture_text("thin.html"), THIN_URL, robots_text=robots, now=NOW)
    ids = [r.signal_id for r in audit.recommendations]
    assert ids[0] == "crawl_access"
    points = [r.points for r in audit.recommendations[1:]]
    assert points == sorted(points, reverse=True)


def test_the_audit_is_deterministic() -> None:
    page = fixture_text("well-structured.html")
    assert run(page, GOOD_URL) == run(page, GOOD_URL)


def test_empty_and_garbage_input_still_produce_an_audit() -> None:
    for html in ("", "   ", "\x00\x01<<<>>>", "<html></html>"):
        audit = run(html)
        assert 0 <= audit.score <= 100
        assert datetime.now(UTC) > audit.audited_at
