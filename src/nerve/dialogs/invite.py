"""Confirmation humaine des invitations — décision explicite avant de
rejoindre un salon.

Modal `InviteDialog` extrait de `app.py`. `themes.accent()` remplace
l'ex-global ACCENT (cf. NOTES.md).
"""

from __future__ import annotations

from nio import MatrixRoom
from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import themes
from ..matrix_client import MatuiClient


class InviteDialog(ModalScreen[None]):
    """Asks for an explicit decision before joining a room."""

    def __init__(
        self,
        client: MatuiClient,
        room_id: str,
        room: MatrixRoom,
        inviter: str,
    ) -> None:
        super().__init__()
        self.client = client
        self.room_id = room_id
        self.room = room
        self.inviter = inviter

    def compose(self) -> ComposeResult:
        name = self.room.display_name or self.room_id
        accent = themes.accent()
        with Vertical(id="invite-dialog"):
            yield Static("Room invitation", id="invite-title")
            yield Static(
                f"[bold]{escape(name)}[/bold]\n"
                f"[dim]{escape(self.room_id)}[/dim]",
                id="invite-room",
            )
            yield Static(
                f"from [bold][{accent}]{escape(self.inviter)}[/{accent}][/bold]",
                id="invite-sender",
            )
            yield Static(
                "Join this room? A malicious inviter could spam or trick you.",
                id="invite-hint",
            )
            with Horizontal(id="invite-actions"):
                yield Button("Accept", id="invite-accept", variant="success", classes="-primary")
                yield Button("Decline", id="invite-decline", variant="error", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#invite-decline", Button).focus()

    async def _finish(self) -> None:
        self.dismiss()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "invite-accept":
            await self.client.accept_invite(self.room_id)
            self.app.notify("Room joined")
        else:  # invite-decline
            await self.client.decline_invite(self.room_id)
            self.app.notify("Invitation declined")
        # L'écran de chat actualise sa liste au prochain sync (le salon rejoint
        # ou refusé apparaîtra / disparaîtra alors).
        await self._finish()