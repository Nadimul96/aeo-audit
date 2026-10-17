from __future__ import annotations

from aeo_audit.page import declared_types, parse_page


def test_headings_text_and_boilerplate_are_separated() -> None:
    page = parse_page(
        "<nav><a href='/'>Home</a></nav><main><h1>Title</h1><p>Body text.</p></main>"
        "<footer><p>Footer words</p></footer>",
        "https://site.example/",
    )
    assert [(b.kind, b.level, b.text) for b in page.blocks] == [
        ("heading", 1, "Title"),
        ("text", 0, "Body text."),
    ]
    assert "main" in page.landmarks


def test_script_style_and_template_text_is_never_content() -> None:
    page = parse_page(
        "<style>.a{}</style><script>var x = 'hello world';</script><template><p>no</p></template>"
        "<p>visible</p>",
        "https://site.example/",
    )
    assert page.text == "visible"
    assert page.script_count == 1


def test_a_head_that_is_never_closed_does_not_swallow_the_body() -> None:
    page = parse_page("<html><head><title>T</title><body><p>kept</p></body>", "https://s.example/")
    assert page.title == "T"
    assert page.text == "kept"


def test_self_closing_svg_does_not_hide_later_content() -> None:
    page = parse_page("<svg/><p>still here</p>", "https://s.example/")
    assert page.text == "still here"


def test_unclosed_paragraphs_still_split_into_blocks() -> None:
    page = parse_page("<p>one<p>two<li>three", "https://s.example/")
    assert [b.text for b in page.blocks] == ["one", "two", "three"]


def test_text_outside_any_block_still_counts() -> None:
    page = parse_page("<div>loose words in a div</div>", "https://s.example/")
    assert page.word_count == 5


def test_links_are_resolved_classified_and_filtered() -> None:
    page = parse_page(
        "<main><a href='/a'>A</a><a href='https://x.org/b' rel='nofollow'>B</a>"
        "<a href='mailto:x@y.z'>mail</a><a href='#top'>top</a><a href='javascript:void(0)'>js</a>"
        "</main><nav><a href='/n'>N</a></nav>",
        "https://site.example/dir/page",
    )
    by_href = {link.href: link for link in page.links}
    assert set(by_href) == {"https://site.example/a", "https://x.org/b", "https://site.example/n"}
    assert by_href["https://site.example/a"].in_content
    assert not by_href["https://site.example/n"].in_content
    assert "nofollow" in by_href["https://x.org/b"].rel


def test_meta_title_lang_canonical_and_times() -> None:
    page = parse_page(
        '<html lang="en"><head><title>  A   title </title><meta name="Description" content=" d ">'
        '<link rel="canonical" href="https://s.example/c"></head>'
        '<body><time datetime="2026-01-02">x</time></body></html>',
        "https://s.example/",
    )
    assert (page.lang, page.title, page.meta["description"]) == ("en", "A title", "d")
    assert page.canonical == "https://s.example/c"
    assert page.times == ["2026-01-02"]


def test_json_ld_is_parsed_nested_and_broken_blocks_are_counted() -> None:
    html = """
    <script type="application/ld+json">
      {"@graph": [{"@type": ["Article", "NewsArticle"], "author": {"@type": "Person"}}]}
    </script>
    <script type="application/ld+json">{ not json </script>
    """
    page = parse_page(html, "https://s.example/")
    assert page.jsonld_errors == 1
    kinds = [declared_types(node) for node in page.nodes()]
    assert ["Article", "NewsArticle"] in kinds
    assert ["Person"] in kinds


def test_schema_org_url_prefixes_are_stripped_from_types() -> None:
    assert declared_types({"@type": "https://schema.org/FAQPage"}) == ["FAQPage"]


def test_noscript_text_and_app_shell_are_detected() -> None:
    page = parse_page(
        '<div id="root"></div><noscript>You need to enable JavaScript.</noscript>',
        "https://s.example/",
    )
    assert page.root_shell
    assert "JavaScript" in page.noscript_text
    assert page.word_count == 0


def test_hostile_markup_does_not_crash_the_parser() -> None:
    page = parse_page("<<>><a href=><p <h1>>x</p></a></div></div><h9>y", "https://s.example/")
    assert isinstance(page.text, str)
