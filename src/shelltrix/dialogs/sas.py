"""Vérification d'appareil par emoji (SAS) — confirmation humaine requise.

Modal `SasDialog` extrait de `app.py`. Lit `themes.accent()` pour l'id
d'appareil (ex-global ACCENT, cf. NOTES.md).
"""

from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import themes
from ..matrix_client import ShelltrixClient


class SasDialog(ModalScreen[None]):
    """Shows the verification emojis and demands a human decision."""

    def __init__(
        self,
        client: ShelltrixClient,
        transaction_id: str,
        user_id: str,
        device_id: str,
        emojis: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.client = client
        self.transaction_id = transaction_id
        self.user_id = user_id
        self.device_id = device_id
        self.emojis = emojis

    def compose(self) -> ComposeResult:
        accent = themes.accent()
        with Vertical(id="sas-dialog"):
            yield Static("Device verification", id="sas-title")
            yield Static(
                f"[dim]{escape(self.user_id)}[/dim] [dim]· device[/dim] "
                f"[{accent}]{escape(self.device_id)}[/{accent}]",
                id="sas-device",
            )
            yield Static(
                "Compare these emojis with the ones shown by the other device.",
                id="sas-hint",
            )
            with Vertical(id="sas-emojis"):
                for emoji, desc in self.emojis:
                    yield Static(
                        f"[bold]{escape(emoji)}[/bold]  [dim]{escape(desc)}[/dim]",
                        classes="sas-emoji",
                    )
            with Horizontal(id="sas-actions"):
                yield Button("Verify", id="sas-confirm", variant="success", classes="-primary")
                yield Button("Reject", id="sas-reject", variant="error", classes="-danger")
                yield Button("Cancel", id="sas-cancel")

    def on_mount(self) -> None:
        self.query_one("#sas-confirm", Button).focus()

    async def _finish(self) -> None:
        self.dismiss()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sas-confirm":
            await self.client.confirm_sas(self.transaction_id)
            self.app.notify("Device verified")
        elif event.button.id == "sas-reject":
            await self.client.reject_sas(self.transaction_id)
            self.app.notify("Verification rejected: the emojis do not match")
        else:  # sas-cancel
            await self.client.cancel_sas(self.transaction_id)
            self.app.notify("Verification cancelled")
        await self._finish()