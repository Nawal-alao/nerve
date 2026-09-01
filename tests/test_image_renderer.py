"""Tests pour le module image_renderer."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from nerve.image_renderer import (
    _guess_extension,
    is_image_message,
    render_image_placeholder,
    get_protocol,
    reset_cache,
    _detect_terminal,
    format_image_message,
)


class TestGuessExtension:
    """Tests pour _guess_extension()."""

    def test_png_extension(self) -> None:
        assert _guess_extension("abc123.png") == ".png"

    def test_jpg_extension(self) -> None:
        assert _guess_extension("photo.jpg") == ".jpg"

    def test_jpeg_extension(self) -> None:
        assert _guess_extension("photo.jpeg") == ".jpeg"

    def test_no_extension_defaults_png(self) -> None:
        assert _guess_extension("abcdef123456") == ".png"

    def test_unknown_extension_defaults_png(self) -> None:
        assert _guess_extension("file.xyz") == ".png"


class TestIsImageMessage:
    """Tests pour is_image_message()."""

    def test_detects_marker(self) -> None:
        assert is_image_message("__NERVE_IMAGE__:/path/to/img.png") is True

    def test_rejects_plain_text(self) -> None:
        assert is_image_message("hello world") is False

    def test_rejects_empty(self) -> None:
        assert is_image_message("") is False


class TestRenderImagePlaceholder:
    """Tests pour render_image_placeholder()."""

    def test_includes_filename(self) -> None:
        result = render_image_placeholder("photo.png")
        assert "photo.png" in result

    def test_returns_string(self) -> None:
        result = render_image_placeholder("test.jpg")
        assert isinstance(result, str)


class TestDetectTerminal:
    """Tests pour _detect_terminal()."""

    def test_kitty_detected(self) -> None:
        with patch.dict(os.environ, {"TERM_PROGRAM": "kitty"}):
            reset_cache()
            assert _detect_terminal() == "kitty"

    def test_wezterm_detected(self) -> None:
        with patch.dict(os.environ, {"TERM_PROGRAM": "wezterm"}):
            reset_cache()
            assert _detect_terminal() == "kitty"  # WezTerm uses Kitty protocol

    def test_ghostty_detected(self) -> None:
        with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}):
            reset_cache()
            assert _detect_terminal() == "kitty"

    def test_kitty_window_id(self) -> None:
        with patch.dict(os.environ, {"KITTY_WINDOW_ID": "1"}):
            reset_cache()
            assert _detect_terminal() == "kitty"

    def test_xterm_detected(self) -> None:
        with patch.dict(os.environ, {"TERM": "xterm-256color"}, clear=True):
            reset_cache()
            assert _detect_terminal() == "sixel"

    def test_unknown_terminal(self) -> None:
        with patch.dict(os.environ, {"TERM": "unknown"}, clear=True):
            reset_cache()
            assert _detect_terminal() == "none"


class TestFormatImageMessage:
    """Tests pour format_image_message()."""

    def test_returns_placeholder_when_no_protocol(self) -> None:
        with patch("nerve.image_renderer.get_protocol", return_value="none"):
            result = format_image_message(
                "Alice",
                "mxc://server/abc123",
                "photo.png",
                "token",
                "https://matrix.org",
            )
            assert "[image:" in result
            assert "photo.png" in result

    def test_returns_marker_when_protocol_available(self) -> None:
        with patch("nerve.image_renderer.get_protocol", return_value="kitty"):
            with patch("nerve.image_renderer.download_image", return_value=Path("/tmp/img.png")):
                result = format_image_message(
                    "Alice",
                    "mxc://server/abc123",
                    "photo.png",
                    "token",
                    "https://matrix.org",
                )
                assert result.startswith("__NERVE_IMAGE__:")
