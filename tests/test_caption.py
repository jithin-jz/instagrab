"""Tests for caption escaping and truncation."""

from __future__ import annotations

from app.services.telegram_bot import CAPTION_LIMIT, build_caption, truncate_caption


def test_caption_escapes_html_special_chars() -> None:
    caption = "<b>boom</b> & friends"
    output = build_caption(caption, "https://example.test/p/abc")
    assert "<b>" not in output.split("\n")[0]
    assert "&lt;b&gt;boom&lt;/b&gt; &amp; friends" in output


def test_caption_includes_safe_link() -> None:
    permalink = 'https://example.test/p/abc"onclick=evil'
    output = build_caption("hello", permalink)
    assert 'href="https://example.test/p/abc&quot;onclick=evil"' in output


def test_truncate_long_caption() -> None:
    long_caption = "x" * (CAPTION_LIMIT + 100)
    assert len(truncate_caption(long_caption)) == CAPTION_LIMIT


def test_truncate_empty_caption() -> None:
    assert truncate_caption("") == ""
