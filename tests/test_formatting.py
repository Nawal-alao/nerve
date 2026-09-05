"""Tests pour le module formatting."""

from __future__ import annotations

import pytest

from shelltrix.formatting import (
    _CODE_SPAN,
    _URL_RE,
    _BOLD_SPAN,
    _ITALIC_SPAN,
    _sender_color,
    _inline_markdown,
    _format_time,
    _fuzzy_score,
)


class TestSenderColor:
    """Tests pour _sender_color."""

    def test_returns_hex_color(self) -> None:
        color = _sender_color("@alice:matrix.org")
        assert color.startswith("#")
        assert len(color) == 7

    def test_stable_for_same_sender(self) -> None:
        color = _sender_color("@alice:matrix.org")
        assert _sender_color("@alice:matrix.org") == color

    def test_different_for_different_senders(self) -> None:
        # MD5 hash can have collisions for similar strings, use diverse names
        color1 = _sender_color("@alice:matrix.org")
        color2 = _sender_color("@charlie:matrix.org")
        assert color1 != color2


class TestInlineMarkdown:
    """Tests pour _inline_markdown."""

    def test_escapes_brackets(self) -> None:
        result = _inline_markdown("[link](url)")
        assert "\\[" in result or "[link]" not in result

    def test_bold_markdown(self) -> None:
        result = _inline_markdown("**bold text**")
        assert "bold text" in result
        assert "[bold]" in result

    def test_italic_markdown(self) -> None:
        result = _inline_markdown("*italic text*")
        assert "italic text" in result
        assert "[italic]" in result

    def test_code_markdown(self) -> None:
        result = _inline_markdown("`code`")
        assert "code" in result
        assert "[/" in result  # Has closing tag

    def test_plain_text_unchanged(self) -> None:
        result = _inline_markdown("just plain text")
        assert "just plain text" in result

    def test_strikethrough_markdown(self) -> None:
        result = _inline_markdown("~~gone~~")
        assert "gone" in result
        assert "[strike]" in result

    def test_combined_inline_styles(self) -> None:
        result = _inline_markdown("**bold** and *italic* and ~~strike~~")
        assert "[bold]" in result
        assert "[italic]" in result
        assert "[strike]" in result


class TestFormatTime:
    """Tests pour _format_time."""

    def test_returns_hh_mm_format(self) -> None:
        # 2024-01-01 12:00:00 UTC
        result = _format_time(1704110400000)
        assert ":" in result
        assert len(result) == 5  # "HH:MM"

    def test_empty_for_none(self) -> None:
        assert _format_time(None) == ""

    def test_empty_for_zero(self) -> None:
        assert _format_time(0) == ""


class TestFuzzyScore:
    """Tests pour _fuzzy_score."""

    def test_exact_match(self) -> None:
        assert _fuzzy_score("test", "test") > 0

    def test_subsequence_match(self) -> None:
        assert _fuzzy_score("tc", "test case") >= 0

    def test_no_match(self) -> None:
        assert _fuzzy_score("xyz", "test case") == -1.0

    def test_empty_query(self) -> None:
        assert _fuzzy_score("", "anything") == 0.0

    def test_prefix_bonus(self) -> None:
        score_prefix = _fuzzy_score("tes", "test")
        score_subseq = _fuzzy_score("tst", "test case")
        assert score_prefix > score_subseq

    def test_case_insensitive(self) -> None:
        assert _fuzzy_score("TEST", "test") > 0


class TestUrlRegex:
    """Tests pour _URL_RE."""

    def test_matches_http_url(self) -> None:
        match = _URL_RE.search("Check http://example.com")
        assert match is not None
        assert "example.com" in match.group()

    def test_matches_https_url(self) -> None:
        match = _URL_RE.search("Check https://example.com/path")
        assert match is not None

    def test_no_match_plain_text(self) -> None:
        match = _URL_RE.search("just plain text")
        assert match is None
