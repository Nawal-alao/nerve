"""Tests pour le contrat async des handlers de ChatScreen.

Tous les handlers assignés à self.client.on_* doivent être des coroutines :
NeuriteClient les await (ex. matrix_client._handle_typing fait
`await self.on_typing(...)`), donc une fonction synchrone assignée à la place
planterait avec un TypeError sur chaque événement.
"""

from __future__ import annotations

import inspect

from neurite.screens.chat import ChatScreen


def test_typing_handler_is_coroutine() -> None:
    """_handle_typing doit être async pour satisfaire TypingHandler."""
    assert inspect.iscoroutinefunction(ChatScreen._handle_typing)


def test_all_client_handlers_are_coroutines() -> None:
    """Chaque handler branché sur self.client.on_* dans on_mount doit être
    async, sinon le await côté NeuriteClient échoue à l'exécution."""
    for name in (
        "_handle_incoming_message",
        "_handle_incoming_image",
        "_handle_typing",
        "_show_invite_dialog",
        "_show_sas_dialog",
        "_on_send_error",
    ):
        assert inspect.iscoroutinefunction(getattr(ChatScreen, name)), name