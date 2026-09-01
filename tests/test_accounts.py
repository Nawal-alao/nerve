"""Tests pour le module accounts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from nerve.accounts import (
    AccountInfo,
    AccountManager,
    _make_label,
    ACCOUNTS_FILE,
)


class TestAccountInfo:
    """Tests pour AccountInfo."""

    def test_to_dict(self) -> None:
        info = AccountInfo(
            user_id="@alice:matrix.org",
            homeserver="https://matrix.org",
            device_id="DEVICE123",
            label="alice — matrix.org",
        )
        d = info.to_dict()
        assert d["user_id"] == "@alice:matrix.org"
        assert d["homeserver"] == "https://matrix.org"
        assert d["device_id"] == "DEVICE123"
        assert d["label"] == "alice — matrix.org"

    def test_from_dict(self) -> None:
        data = {
            "user_id": "@alice:matrix.org",
            "homeserver": "https://matrix.org",
            "device_id": "DEVICE123",
            "label": "alice — matrix.org",
        }
        info = AccountInfo.from_dict(data)
        assert info.user_id == "@alice:matrix.org"

    def test_round_trip(self) -> None:
        original = AccountInfo(
            user_id="@bob:server.com",
            homeserver="https://server.com",
            device_id="DEV456",
            label="bob — server.com",
        )
        restored = AccountInfo.from_dict(original.to_dict())
        assert restored == original


class TestMakeLabel:
    """Tests pour _make_label()."""

    def test_simple_user_id(self) -> None:
        label = _make_label("@alice:matrix.org", "https://matrix.org")
        assert "@alice" in label
        assert "matrix.org" in label

    def test_strips_protocol(self) -> None:
        label = _make_label("@bob:server.com", "https://server.com")
        assert "https://" not in label

    def test_handles_no_protocol(self) -> None:
        label = _make_label("@charlie:my.server", "my.server")
        assert "my.server" in label


class TestAccountManager:
    """Tests pour AccountManager."""

    def test_empty_on_creation(self, tmp_path: Path) -> None:
        with patch("nerve.accounts.ACCOUNTS_FILE", tmp_path / "accounts.json"):
            mgr = AccountManager()
            assert mgr.count() == 0
            assert mgr.accounts == []

    def test_add_account(self, tmp_path: Path) -> None:
        from nerve.config import Credentials

        with patch("nerve.accounts.ACCOUNTS_FILE", tmp_path / "accounts.json"):
            with patch("nerve.accounts.CONFIG_DIR", tmp_path):
                mgr = AccountManager()
                creds = Credentials(
                    homeserver="https://matrix.org",
                    user_id="@alice:matrix.org",
                    device_id="DEV123",
                    access_token="token123",
                )
                info = mgr.add(creds)
                assert mgr.count() == 1
                assert info.user_id == "@alice:matrix.org"

    def test_remove_account(self, tmp_path: Path) -> None:
        from nerve.config import Credentials

        with patch("nerve.accounts.ACCOUNTS_FILE", tmp_path / "accounts.json"):
            with patch("nerve.accounts.CONFIG_DIR", tmp_path):
                mgr = AccountManager()
                creds = Credentials(
                    homeserver="https://matrix.org",
                    user_id="@alice:matrix.org",
                    device_id="DEV123",
                    access_token="token123",
                )
                mgr.add(creds)
                assert mgr.count() == 1
                mgr.remove("@alice:matrix.org")
                assert mgr.count() == 0

    def test_get_by_user_id(self, tmp_path: Path) -> None:
        from nerve.config import Credentials

        with patch("nerve.accounts.ACCOUNTS_FILE", tmp_path / "accounts.json"):
            with patch("nerve.accounts.CONFIG_DIR", tmp_path):
                mgr = AccountManager()
                creds = Credentials(
                    homeserver="https://matrix.org",
                    user_id="@alice:matrix.org",
                    device_id="DEV123",
                    access_token="token123",
                )
                mgr.add(creds)
                found = mgr.get("@alice:matrix.org")
                assert found is not None
                assert found.user_id == "@alice:matrix.org"

    def test_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        with patch("nerve.accounts.ACCOUNTS_FILE", tmp_path / "accounts.json"):
            mgr = AccountManager()
            assert mgr.get("@nobody:matrix.org") is None
