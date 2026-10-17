"""Turn HTML into the small, ordered model the signals read.

Only the standard library's tolerant `html.parser` is used. No JavaScript runs:
that is deliberate, because it shows the page the way a crawler that does not
render scripts would see it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

_SKIPPED = frozenset({"script", "style", "noscript", "template", "svg", "head"})
_BOILERPLATE = frozenset({"nav", "footer", "aside", "header"})
_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_TEXT_BLOCKS = frozenset({"p", "li", "blockquote", "dd"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"})
_WORD = re.compile(r"[\w'’-]+")


@dataclass(frozen=True, slots=True)
class Block:
    kind: str  # "heading" or "text"
    level: int  # 1-6 for headings, 0 for text
    text: str

    @property
    def words(self) -> int:
        return len(_WORD.findall(self.text))


@dataclass(frozen=True, slots=True)
class Link:
    href: str
    text: str
    rel: frozenset[str]
    in_content: bool


@dataclass(slots=True)
class Page:
    url: str
    lang: str = ""
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    canonical: str = ""
    blocks: list[Block] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    landmarks: set[str] = field(default_factory=set)
    jsonld: list[Any] = field(default_factory=list)
    jsonld_errors: int = 0
    script_count: int = 0
    noscript_text: str = ""
    root_shell: bool = False

    @property
    def text(self) -> str:
        return " ".join(block.text for block in self.blocks)

    @property
    def word_count(self) -> int:
        return sum(block.words for block in self.blocks)

    def headings(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "heading"]

    def nodes(self) -> list[dict[str, Any]]:
        """Every JSON-LD object that declares an `@type`, however deeply nested."""
        found: list[dict[str, Any]] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if "@type" in value:
                    found.append(value)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.jsonld)
        return found


def declared_types(node: dict[str, Any]) -> list[str]:
    """The node's `@type` values as written, without any schema.org URL prefix."""
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    return [str(v).rsplit("/", 1)[-1] for v in values if isinstance(v, str)]


def type_names(node: dict[str, Any]) -> list[str]:
    """`declared_types`, lower-cased for matching."""
    return [name.lower() for name in declared_types(node)]


class _Parser(HTMLParser):
    def __init__(self, url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page(url=url)
        self._skip = 0
        self._boilerplate = 0
        self._stack: list[str] = []
        self._block: tuple[str, int] | None = None
        self._buffer: list[str] = []
        self._anchor: dict[str, Any] | None = None
        self._anchor_text: list[str] = []
        self._capture: str | None = None
        self._capture_buffer: list[str] = []
        self._title: list[str] = []
        self._in_title = False

    # --- tags -------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k.lower(): (v or "") for k, v in attrs}
        self._open(tag, attributes)
        if tag in _VOID:
            return
        self._stack.append(tag)
        if tag == "body":
            self._skip = 0  # tolerate a <head> that was never closed
        elif tag in _SKIPPED:
            self._skip += 1
        if tag in _BOILERPLATE:
            self._boilerplate += 1
        if not self._skip and (tag in _HEADINGS or tag in _TEXT_BLOCKS):
            self._flush()
            self._block = ("heading" if tag in _HEADINGS else "text", _HEADINGS.get(tag, 0))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, {k.lower(): (v or "") for k, v in attrs})

    def _open(self, tag: str, attributes: dict[str, str]) -> None:
        self._open_head(tag, attributes)
        self._open_body(tag, attributes)

    def _open_head(self, tag: str, attributes: dict[str, str]) -> None:
        page = self.page
        if tag == "html":
            page.lang = attributes.get("lang", "")
        elif tag == "meta":
            key = (attributes.get("name") or attributes.get("property") or "").lower()
            if key and "content" in attributes:
                page.meta.setdefault(key, attributes["content"].strip())
        elif tag == "link":
            rel = attributes.get("rel", "").lower().split()
            if "canonical" in rel:
                page.canonical = attributes.get("href", "")
            if "author" in rel and attributes.get("href"):
                page.links.append(Link(attributes["href"], "", frozenset(rel), in_content=False))
        elif tag == "title":
            self._in_title = True

    def _open_body(self, tag: str, attributes: dict[str, str]) -> None:
        page = self.page
        if tag == "script":
            page.script_count += 1
            if "ld+json" in attributes.get("type", "").lower():
                self._capture, self._capture_buffer = "jsonld", []
        elif tag == "noscript":
            self._capture, self._capture_buffer = "noscript", []
        elif tag == "time" and attributes.get("datetime"):
            page.times.append(attributes["datetime"])
        elif tag in ("main", "article"):
            page.landmarks.add(tag)
        elif tag == "div" and attributes.get("id") in ("root", "app", "__next", "__nuxt"):
            page.root_shell = True
        elif tag == "a" and attributes.get("href"):
            self._anchor = {
                "href": attributes["href"],
                "rel": frozenset(attributes.get("rel", "").lower().split()),
                "content": not self._boilerplate,
            }
            self._anchor_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.page.title = " ".join("".join(self._title).split())
            self._in_title = False
        if tag == "script" and self._capture == "jsonld":
            self._finish_jsonld()
        if tag == "noscript" and self._capture == "noscript":
            self.page.noscript_text = " ".join("".join(self._capture_buffer).split())
            self._capture = None
        if tag == "a" and self._anchor is not None:
            text = " ".join("".join(self._anchor_text).split())
            self.page.links.append(
                Link(self._anchor["href"], text, self._anchor["rel"], self._anchor["content"])
            )
            self._anchor = None
        if tag in _HEADINGS or tag in _TEXT_BLOCKS:
            self._flush()
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass
            if tag in _SKIPPED:
                self._skip = max(0, self._skip - 1)
            if tag in _BOILERPLATE:
                self._boilerplate = max(0, self._boilerplate - 1)

    # --- text -------------------------------------------------------------

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        if self._capture is not None:
            self._capture_buffer.append(data)
        if self._skip:
            return
        if self._anchor is not None:
            self._anchor_text.append(data)
        if self._block is not None and not self._boilerplate:
            self._buffer.append(data)
        elif self._block is None and not self._boilerplate and data.strip():
            # Text outside any <p>/<li>/heading (common in div soup) still counts as content.
            self.page.blocks.append(Block("text", 0, " ".join(data.split())))

    def _flush(self) -> None:
        if self._block is not None:
            text = " ".join("".join(self._buffer).split())
            if text and not self._boilerplate:
                self.page.blocks.append(Block(self._block[0], self._block[1], text))
        self._block, self._buffer = None, []

    def _finish_jsonld(self) -> None:
        raw = "".join(self._capture_buffer).strip()
        self._capture = None
        try:
            self.page.jsonld.append(json.loads(raw))
        except ValueError:
            self.page.jsonld_errors += 1

    def close(self) -> None:
        super().close()
        self._flush()


def parse_page(html: str, url: str) -> Page:
    """Parse `html`, resolving relative links against `url`."""
    parser = _Parser(url)
    parser.feed(html)
    parser.close()
    page = parser.page
    page.links = [
        Link(urljoin(url, link.href), link.text, link.rel, link.in_content)
        for link in page.links
        if _is_web_link(link.href)
    ]
    return page


def _is_web_link(href: str) -> bool:
    scheme = urlsplit(href).scheme.lower()
    return scheme in ("", "http", "https") and not href.startswith("#")
