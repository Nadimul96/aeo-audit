"""Metamorphic tests: changes that should only hurt must never raise the score, and vice versa.

The weights are judgment calls, so there is no ground truth to test them against.
What can be tested is direction: removing something the audit rewards must not
increase the score, and adding it to a page that lacks it must not decrease it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from hypothesis import given, settings
from hypothesis import strategies as st

from aeo_audit import audit_html
from conftest import GOOD_URL, NOW, THIN_URL, fixture_text

Page = tuple[str, str]  # (html, robots.txt)
Mutation = Callable[[Page], Page]

ROBOTS = fixture_text("robots-open.txt")


def strip_json_ld(page: Page) -> Page:
    html, robots = page
    return re.sub(
        r"<script type=\"application/ld\+json\">.*?</script>", "", html, flags=re.S
    ), robots


def strip_authorship(page: Page) -> Page:
    html, robots = page
    html = re.sub(r'<meta name="author"[^>]*>', "", html)
    html = html.replace("By Maya Okafor, head roaster. ", "")
    html = html.replace(' rel="author"', "")
    return html, robots


def strip_dates(page: Page) -> Page:
    html, robots = page
    return re.sub(r'<meta property="article:(published|modified)_time"[^>]*>', "", html), robots


def flatten_headings(page: Page) -> Page:
    html, robots = page
    return re.sub(r"<(/?)h[1-6]>", r"<\1p>", html), robots


def unwrap_links(page: Page) -> Page:
    html, robots = page
    return re.sub(r"<a [^>]*>(.*?)</a>", r"\1", html, flags=re.S), robots


def blur_numbers(page: Page) -> Page:
    html, robots = page
    body = html.split("<body>", 1)
    return body[0] + "<body>" + re.sub(r"\d+", "many", body[1]), robots


def drop_landmarks(page: Page) -> Page:
    html, robots = page
    return re.sub(r"</?(main|article)>", "", html), robots


def block_search_crawlers(page: Page) -> Page:
    html, robots = page
    return html, robots + "\nUser-agent: OAI-SearchBot\nUser-agent: Claude-SearchBot\nDisallow: /\n"


def block_everything(page: Page) -> Page:
    html, robots = page
    return html, robots + "\nUser-agent: *\nDisallow: /\n"


DEGRADE: list[Mutation] = [
    strip_json_ld,
    strip_authorship,
    strip_dates,
    flatten_headings,
    unwrap_links,
    blur_numbers,
    drop_landmarks,
    block_search_crawlers,
    block_everything,
]


def score(page: Page, url: str) -> int:
    return audit_html(page[0], url, robots_text=page[1], now=NOW).score


@settings(max_examples=60, deadline=None)
@given(st.lists(st.sampled_from(DEGRADE), min_size=1, max_size=9))
def test_removing_things_the_audit_rewards_never_raises_the_score(
    mutations: list[Mutation],
) -> None:
    page: Page = (fixture_text("well-structured.html"), ROBOTS)
    previous = score(page, GOOD_URL)
    for mutate in mutations:
        page = mutate(page)
        current = score(page, GOOD_URL)
        assert current <= previous, f"{mutate.__name__} raised the score {previous} -> {current}"
        previous = current


def add_json_ld(page: Page) -> Page:
    html, robots = page
    block = (
        '<script type="application/ld+json">{"@type":"Article","headline":"Home",'
        '"author":"Pat Lee","datePublished":"2026-09-01"}</script>'
    )
    return html.replace("</head>", block + "</head>"), robots


def add_author_and_dates(page: Page) -> Page:
    html, robots = page
    meta = (
        '<meta name="author" content="Pat Lee">'
        '<meta property="article:published_time" content="2026-09-01">'
    )
    return html.replace("</head>", meta + "</head>"), robots


def add_document_basics(page: Page) -> Page:
    html, robots = page
    html = html.replace("<html>", '<html lang="en">')
    html = html.replace("<title>Home</title>", "<title>Harbor Roast: small-batch coffee</title>")
    head = (
        '<meta name="description" content="Small-batch coffee roasted in Maine and shipped '
        'within two days of roasting.">'
        '<link rel="canonical" href="https://harborroast.example/">'
    )
    html = html.replace("</head>", head + "</head>")
    return html.replace("<body>", "<body><main>").replace("</body>", "</main></body>"), robots


def fix_headings(page: Page) -> Page:
    html, robots = page
    html = html.replace(
        "<h1>The Coffee Experience You Deserve</h1>", "<h2>The Coffee Experience You Deserve</h2>"
    )
    return html, robots


def add_robots_allow_note(page: Page) -> Page:
    html, robots = page
    return html, robots + "\nUser-agent: OAI-SearchBot\nAllow: /\n"


IMPROVE: list[Mutation] = [
    add_json_ld,
    add_author_and_dates,
    add_document_basics,
    fix_headings,
    add_robots_allow_note,
]


@settings(max_examples=60, deadline=None)
@given(st.lists(st.sampled_from(IMPROVE), min_size=1, max_size=5))
def test_adding_markup_and_metadata_never_lowers_the_score(mutations: list[Mutation]) -> None:
    page: Page = (fixture_text("thin.html"), ROBOTS)
    previous = score(page, THIN_URL)
    for mutate in mutations:
        page = mutate(page)
        current = score(page, THIN_URL)
        assert current >= previous, f"{mutate.__name__} lowered the score {previous} -> {current}"
        previous = current


def test_the_mutations_really_change_the_pages() -> None:
    good: Page = (fixture_text("well-structured.html"), ROBOTS)
    for mutate in DEGRADE:
        assert mutate(good) != good, f"{mutate.__name__} did nothing, so its test proves nothing"
    thin: Page = (fixture_text("thin.html"), ROBOTS)
    for mutate in (add_json_ld, add_author_and_dates, add_document_basics, fix_headings):
        assert mutate(thin) != thin, f"{mutate.__name__} did nothing"
