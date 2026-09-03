"""Tests pour l'autocomplétion des mentions @user / #room.

Cible les helpers purs de ChatScreen (parsing de mention, liste des
utilisateurs d'un salon, liste des salons) sans avoir à monter l'app
Textual complète.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from nerve.screens.chat import ChatScreen


def make_screen(client: object | None = None) -> ChatScreen:
    """Créé un ChatScreen avec un client mocké, sans le monter."""
    if client is None:
        client = MagicMock()
        client.client.user_id = "@me:hs"
        client.rooms.return_value = {}
    return ChatScreen(client)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Parsing du trigger de mention
# ----------------------------------------------------------------------
def test_find_mention_start_user() -> None:
    sc = make_screen()
    assert sc._find_mention_start("hello @ali", 10) == (6, "user", "ali")


def test_find_mention_start_room() -> None:
    sc = make_screen()
    assert sc._find_mention_start("look #mat", 9) == (5, "room", "mat")


def test_find_mention_start_no_mention() -> None:
    sc = make_screen()
    assert sc._find_mention_start("hello world", 11) is None


def test_mention_must_follow_space_or_start() -> None:
    """Un @ au milieu d'un mot ne déclenche pas la complétion."""
    sc = make_screen()
    # "a@b" : le @ n'est pas en début de mot → None
    assert sc._find_mention_start("a@b c", 3) is None


def test_mention_with_space_is_not_completed() -> None:
    """Une query contenant un espace coupe la mention (on est sorti)."""
    sc = make_screen()
    assert sc._find_mention_start("@ali bob", 6) is None


def test_mention_at_start() -> None:
    sc = make_screen()
    assert sc._find_mention_start("@alice", 6) == (0, "user", "alice")


def test_mix_hash_then_at_uses_nearest() -> None:
    sc = make_screen()
    # Le @ est plus près du curseur que le # → la mention active est @
    assert sc._find_mention_start("#room and @alice", 16) == (10, "user", "alice")


# ----------------------------------------------------------------------
# Liste des utilisateurs d'un salon (exclut l'utilisateur courant)
# ----------------------------------------------------------------------
def test_active_room_users_excludes_self() -> None:
    room = MagicMock()
    room.users = {"@me:hs": object(), "@alice:hs": object()}
    room.user_name.side_effect = lambda uid: {"@alice:hs": "Alice"}.get(uid)
    client = MagicMock()
    client.client.user_id = "@me:hs"
    client.rooms.return_value = {"!r:hs": room}
    sc = make_screen(client)
    sc.active_room_id = "!r:hs"
    users = sc._active_room_users()
    assert users == [("@alice:hs", "Alice")]


def test_active_room_users_no_active_room() -> None:
    sc = make_screen()
    assert sc._active_room_users() == []


# ----------------------------------------------------------------------
# Liste des salons (alias préféré, sinon id)
# ----------------------------------------------------------------------
def test_all_rooms_prefers_alias() -> None:
    room_a = MagicMock(canonical_alias="#alias:hs", display_name="Room A")
    room_b = MagicMock(canonical_alias=None, display_name="Room B")
    client = MagicMock()
    client.client.user_id = "@me:hs"
    client.rooms.return_value = {"!a:hs": room_a, "!b:hs": room_b}
    sc = make_screen(client)
    rooms = sc._all_rooms()
    # Trit par nom d'affichage : Room A avant Room B
    assert rooms == [("#alias:hs", "Room A"), ("!b:hs", "Room B")]
