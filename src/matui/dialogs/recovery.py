"""Clé de récupération de session (E2EE) — gestion et restauration.

Modal `RecoveryDialog` extrait de `app.py`. Lit `themes.accent()` pour la
clé affichée (ex-global ACCENT, cf. NOTES.md) et pilote le store via config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .. import themes
from ..config import (
    regenerate_recovery_secret,
    reveal_recovery_secret,
)

if TYPE_CHECKING:
    from ..screens.chat import ChatScreen


class RecoveryDialog(ModalScreen[None]):
    """Montre (ou régénère) la clé de récupération : elle permet de
    restaurer la session (clés E2EE locales) quand le trousseau système
    a perdu la clé du store (changement de machine, trousseau vidé)."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    def __init__(self, chat: ChatScreen) -> None:
        super().__init__()
        self.chat = chat
        self._confirming = False
        self._confirm_timer: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="rec-dialog"):
            yield Static("Session recovery key", id="rec-title")
            yield Static(
                "This key decrypts your local E2EE store when the system "
                "keyring is lost (new machine, wiped keyring). Store it "
                "offline — it cannot be recovered later.",
                id="rec-hint",
            )
            yield Static("[dim]Press Reveal to display the key below.[/dim]", id="rec-key")
            with Horizontal(id="rec-actions"):
                yield Button("Reveal", id="rec-reveal", variant="primary", classes="-primary")
                yield Button("Regenerate", id="rec-regenerate", classes="-danger")
                yield Button("Close", id="rec-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rec-close":
            self.dismiss()
        elif event.button.id == "rec-reveal":
            self._reveal()
        elif event.button.id == "rec-regenerate":
            self._regenerate()

    def _reset_confirm(self) -> None:
        """Revient à l'état de repos : bouton "Regenerate", aucune attente."""
        self._confirming = False
        button = self.query_one("#rec-regenerate", Button)
        button.label = "Regenerate"
        button.variant = "default"
        self._confirm_timer = None

    def _arm_confirm_timeout(self) -> None:
        """Lance (ou relance) le compte à rebours de confirmation d'un 1er clic.

        Si l'utilisateur ne re-clique pas dans les 3 secondes, on revient à
        l'état initial : l'ancienne clé n'a jamais été invalidée. Le timer
        précédent, s'il existe, est d'abord arrêté pour ne pas superposer
        deux expirations.
        """
        if self._confirm_timer is not None:
            self._confirm_timer.stop()
        self._confirm_timer = self.set_timer(3.0, self._expire_confirm)

    def _expire_confirm(self) -> None:
        if not self.is_mounted or not self._confirming:
            return
        self._reset_confirm()
        self.app.notify("Regeneration cancelled — no key was invalidated", title="Recovery key")

    def _set_key(self, secret: str, note: str) -> None:
        accent = themes.accent()
        self.query_one("#rec-key", Static).update(
            f"[bold][{accent}]{secret}[/{accent}][/bold]\n[dim]{note}[/dim]"
        )

    def _reveal(self) -> None:
        try:
            secret = reveal_recovery_secret()
        except Exception as exc:  # noqa: BLE001 — surface l'erreur à l'écran
            self.app.notify(f"Could not reveal the recovery key: {exc}", severity="error")
            return
        self._set_key(secret, "Write this key down and keep it in a safe place.")
        button = self.query_one("#rec-reveal", Button)
        button.disabled = True
        button.label = "Shown"

    def _regenerate(self) -> None:
        button = self.query_one("#rec-regenerate", Button)
        if not self._confirming:
            self._confirming = True
            button.label = "Confirm regenerate?"
            button.variant = "error"
            self._arm_confirm_timeout()
            self.app.notify(
                "Regenerating invalidates the previous recovery key "
                "— click again to confirm",
                title="Recovery key",
            )
            return
        try:
            secret = regenerate_recovery_secret()
        except Exception as exc:  # noqa: BLE001 — surface l'erreur à l'écran
            self.app.notify(f"Could not regenerate the key: {exc}", severity="error")
            self._reset_confirm()
            return
        self._reset_confirm()
        self._set_key(secret, "The previous recovery key is now invalid.")
        self.app.notify("Recovery key regenerated", title="Recovery key")