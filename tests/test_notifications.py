"""Tests pour le module notifications."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from neurite.notifications import is_enabled, notify, CONFIG_FILE


class TestIsEnabled:
    """Tests pour is_enabled()."""

    def test_default_true_when_no_config(self, tmp_path: Path) -> None:
        with patch("neurite.notifications.CONFIG_FILE", tmp_path / "config.json"):
            assert is_enabled() is True

    def test_reads_config_value(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"notifications_enabled": False}))
        with patch("neurite.notifications.CONFIG_FILE", config):
            assert is_enabled() is False

    def test_handles_corrupt_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text("not valid json")
        with patch("neurite.notifications.CONFIG_FILE", config):
            assert is_enabled() is True


class TestNotify:
    """Tests pour notify()."""

    def test_silent_when_disabled(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"notifications_enabled": False}))
        with patch("neurite.notifications.CONFIG_FILE", config):
            with patch("neurite.notifications.subprocess.Popen") as mock_popen:
                notify("Room", "Alice", "Hello")
                mock_popen.assert_not_called()

    def test_silent_when_no_notify_send(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"notifications_enabled": True}))
        with patch("neurite.notifications.CONFIG_FILE", config):
            with patch("neurite.notifications.shutil.which", return_value=None):
                with patch("neurite.notifications.subprocess.Popen") as mock_popen:
                    notify("Room", "Alice", "Hello")
                    mock_popen.assert_not_called()

    def test_calls_notify_send_when_available(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"notifications_enabled": True}))
        mock_popen = MagicMock()
        with patch("neurite.notifications.CONFIG_FILE", config):
            with patch("neurite.notifications.shutil.which", return_value="/usr/bin/notify-send"):
                with patch("neurite.notifications.subprocess.Popen", mock_popen):
                    notify("Room", "Alice", "Hello world")
                    mock_popen.assert_called_once()
                    args = mock_popen.call_args[0][0]
                    assert "notify-send" in args
                    assert "Hello world" in args

    def test_truncates_long_body(self, tmp_path: Path) -> None:
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"notifications_enabled": True}))
        mock_popen = MagicMock()
        long_body = "x" * 300
        with patch("neurite.notifications.CONFIG_FILE", config):
            with patch("neurite.notifications.shutil.which", return_value="/usr/bin/notify-send"):
                with patch("neurite.notifications.subprocess.Popen", mock_popen):
                    notify("Room", "Alice", long_body)
                    args = mock_popen.call_args[0][0]
                    # Body should be truncated to 200 chars
                    body_arg = [a for a in args if len(a) <= 200 and "x" in a]
                    assert len(body_arg[0]) == 200
