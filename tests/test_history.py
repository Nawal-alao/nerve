"""Tests pour le scrollback (historique serveur) côté ChatScreen.

Cible la conversion des événements d'historique nio en TimelineEntry prêtes à
être préfixées (`_entries_from_events`) : ordre chronologique, event_id, type
de message, détection de mention, et placeholder d'image.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from nio import RoomMessageImage, RoomMessageText

from shelltrix.screens.chat import ChatScreen


class _StubRoom:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    def user_name(self, sender: str) -> str | None:
        mapping = {"@alice:hs": "Alice", "@bob:hs": "Bob"}
        return mapping.get(sender)


class _StubInnerClient:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id


class _StubClient:
    """Mini doublure de ShelltrixClient suffisante pour _entries_from_events."""

    def __init__(self) -> None:
        self.client = _StubInnerClient("@me:hs")
        self._rooms = {"!r:hs": _StubRoom("@me:hs")}

    def rooms(self) -> dict[str, _StubRoom]:
        return self._rooms


def make_screen() -> ChatScreen:
    return ChatScreen(_StubClient())  # type: ignore[arg-type]


def text_event(
    sender: str,
    body: str,
    ts: int,
    event_id: str,
    msgtype: str = "m.text",
) -> RoomMessageText:
    ev = MagicMock(spec=RoomMessageText)
    ev.sender = sender
    ev.body = body
    ev.server_timestamp = ts
    ev.event_id = event_id
    ev.msgtype = msgtype
    return ev


def image_event(sender: str, ts: int, event_id: str) -> RoomMessageImage:
    ev = MagicMock(spec=RoomMessageImage)
    ev.sender = sender
    ev.body = "photo.png"
    ev.server_timestamp = ts
    ev.event_id = event_id
    return ev


def test_entries_sorted_chronologically() -> None:
    screen = make_screen()
    later = text_event("@alice:hs", "newer", 3000, "ev3")
    earlier = text_event("@alice:hs", "older", 1000, "ev1")
    middle = text_event("@bob:hs", "middle", 2000, "ev2")
    entries = screen._entries_from_events("!r:hs", [later, earlier, middle])
    assert [e.time_ms for e in entries] == [1000, 2000, 3000]
    assert [e.event_id for e in entries] == ["ev1", "ev2", "ev3"]


def test_mention_detected_in_history() -> None:
    screen = make_screen()
    ev = text_event("@alice:hs", "hé @me regarde ça", 1000, "ev1")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert entries[0].has_mention is True


def test_no_mention_in_history() -> None:
    screen = make_screen()
    ev = text_event("@alice:hs", "salut tout le monde", 1000, "ev1")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert entries[0].has_mention is False


def test_image_entry_is_placeholder() -> None:
    screen = make_screen()
    ev = image_event("@alice:hs", 1000, "ev-img")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert len(entries) == 1
    assert entries[0].is_image is True
    assert entries[0].msgtype == "m.image"
    assert "photo.png" in entries[0].image_hint


def test_own_message_displayed_as_vous() -> None:
    screen = make_screen()
    ev = text_event("@me:hs", "mon message", 1000, "ev1")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert entries[0].is_own is True
    assert entries[0].display_name == "Vous"


def test_display_name_resolved_from_room() -> None:
    screen = make_screen()
    ev = text_event("@alice:hs", "bonjour", 1000, "ev1")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert entries[0].display_name == "Alice"


def test_msgtype_preserved() -> None:
    screen = make_screen()
    ev = text_event("@bob:hs", "* action", 1000, "ev1", msgtype="m.emote")
    entries = screen._entries_from_events("!r:hs", [ev])
    assert entries[0].msgtype == "m.emote"
