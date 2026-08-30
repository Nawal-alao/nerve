"""Rejoindre un salon par alias — saisie d'un #alias:serveur.

Modal `JoinRoomDialog` extrait de `app.py`. N'utilise l'écran de chat que
par instance (`self.chat`) : la classe n'est donc importée que sous
TYPE_CHECKING.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

if TYPE_CHECKING:
    from ..screens.chat import ChatScreen


class JoinRoomDialog(ModalScreen[None]):
    """Small modal asking for the alias of the room to join."""

    BINDINGS = [
        ("escape", "dismiss", "Cancel"),
    ]

    def __init__(self, chat: ChatScreen) -> None:
        super().__init__()
        self.chat = chat

    def compose(self) -> ComposeResult:
        with Vertical(id="jr-dialog"):
            yield Static("Join a room", id="jr-title")
            yield Input(placeholder="#room:server", id="jr-alias")
            with Horizontal(id="jr-buttons"):
                yield Button("Join", id="jr-confirm", variant="primary", classes="-primary")
                yield Button("Cancel", id="jr-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#jr-alias", Input).focus()

    @staticmethod
    def _host_hint(chat: ChatScreen) -> str:
        server = ""
        for room in chat.client.rooms().values():
            canonical = getattr(room, "canonical_alias", None)
            if canonical and ":" in canonical:
                return canonical.rsplit(":", 1)[1]
            room_id_parts = room.room_id.split(":")
            if len(room_id_parts) > 1:
                server = room_id_parts[1]
                break
        return server

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "jr-confirm":
            asyncio.create_task(self._join())
        elif event.button.id == "jr-cancel":
            self.dismiss()
            self.app.call_after_refresh(self.chat.action_focus_input)

    async def _join(self) -> None:
        raw = self.query_one("#jr-alias", Input).value.strip()
        if not raw:
            self.app.notify("Type a room alias", severity="error")
            return
        alias = raw
        if not alias.startswith("#"):
            if ":" not in alias:
                host = self._host_hint(self.chat)
                alias = f"#{alias}:{host}" if host else f"#{alias}"
            else:
                alias = f"#{alias}"
        self.dismiss()
        await self.chat.client.join_room(alias)
        await self.chat._refresh_room_list_async()
        self.app.call_after_refresh(self.chat.action_focus_input)