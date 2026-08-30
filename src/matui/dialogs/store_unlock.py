"""Restauration du store E2EE au démarrage quand la clé du trousseau manque.

Modal `StoreUnlockDialog` extrait de `app.py`. Imports différés de
ChatScreen/LoginScreen tant qu'ils vivent dans app.py (étapes 11 et 12),
cf. NOTES.md.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

# ChatScreen/LoginScreen sont extraits dans screens/ (étapes 11-12) ; ils
# sont importés en haut de module. Le reste des notes : cf. NOTES.md.
from ..config import (
    Credentials,
    StoreLockedError,
    decrypt_store,
    remove_store,
)
from ..matrix_client import MatuiClient
from ..screens.chat import ChatScreen
from ..screens.login import LoginScreen


class StoreUnlockDialog(ModalScreen[None]):
    """Demande la clé de récupération pour déchiffrer le store E2EE au
    démarrage, quand la clé du trousseau est absente (restauration)."""

    BINDINGS = [
        ("escape", "cancel", "Sign out"),
    ]

    def __init__(self, creds: Credentials, client: MatuiClient) -> None:
        super().__init__()
        self.creds = creds
        self.client = client

    def compose(self) -> ComposeResult:
        with Vertical(id="unlock-dialog"):
            yield Static("Recovery key required", id="unlock-title")
            yield Static(
                "Your E2EE session is encrypted at rest and its store key is "
                "missing from the system keyring. Enter the recovery key you "
                "saved with /recovery to restore this session.",
                id="unlock-hint",
            )
            yield Input(placeholder="Recovery key", id="unlock-key")
            yield Label("", id="unlock-status")
            with Horizontal(id="unlock-actions"):
                yield Button("Restore", id="unlock-restore", variant="primary", classes="-primary")
                yield Button("Sign out & start fresh", id="unlock-logout", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#unlock-key", Input).focus()

    def _status(self, message: str, *, kind: str = "") -> None:
        status = self.query_one("#unlock-status", Label)
        status.set_classes(kind)
        status.update(message)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "unlock-restore":
            await self._restore()
        elif event.button.id == "unlock-logout":
            await self._cancel()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "unlock-key":
            await self._restore()

    async def _restore(self) -> None:
        raw = self.query_one("#unlock-key", Input).value
        if not raw.strip():
            self._status("Type your recovery key.", kind="error")
            return
        try:
            decrypt_store(recovery_key=raw)
            # Store déchiffré : on charge maintenant les clés E2EE locales.
            self.client.load_local_store()
        except StoreLockedError as exc:
            self._status(str(exc), kind="error")
            return
        self.dismiss()
        self.app.call_after_refresh(self._go_chat)

    async def _go_chat(self) -> None:
        await self.app.push_screen(ChatScreen(self.client))

    async def _cancel(self) -> None:
        self.creds.remove()
        remove_store()
        self.dismiss()
        self.app.call_after_refresh(self._go_login)

    async def _go_login(self) -> None:
        await self.app.switch_screen(LoginScreen())

    async def action_cancel(self) -> None:
        await self._cancel()