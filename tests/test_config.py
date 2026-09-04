"""Tests pour le module config — fonctions pures."""

from __future__ import annotations

import pytest

from neurite.config import normalize_recovery_key


class TestNormalizeRecoveryKey:
    """Tests pour normalize_recovery_key()."""

    def test_removes_spaces(self) -> None:
        result = normalize_recovery_key("abc def ghi")
        assert " " not in result

    def test_removes_newlines(self) -> None:
        result = normalize_recovery_key("abc\ndef\nghi")
        assert "\n" not in result

    def test_adds_padding(self) -> None:
        # Base64 without padding
        result = normalize_recovery_key("abc")
        # Should add padding
        assert result.endswith("=")

    def test_preserves_valid_base64(self) -> None:
        # Valid base64 with padding
        result = normalize_recovery_key("dGVzdA==")
        assert result == "dGVzdA=="

    def test_handles_empty(self) -> None:
        result = normalize_recovery_key("")
        assert result == ""
