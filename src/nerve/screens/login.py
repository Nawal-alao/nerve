"""Écran de connexion initial — une seule fois, ensuite le token est
réutilisé automatiquement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Rule, Static

from ..matrix_client import NerveClient

if TYPE_CHECKING:
    from ..app import NerveApp


class LoginScreen(Screen):
    """Écran de connexion initial (une seule fois, ensuite le token est
    réutilisé automatiquement)."""

    def compose(self) -> ComposeResult:
        with Vertical(id="login-wrap"):
            with Vertical(id="login-card"):
                yield Static("◆ nerve", id="brand")
                yield Static(
                    "A premium Matrix client, right in your terminal.",
                    id="tagline",
                )
                yield Rule(classes="divider")
                yield Input(
                    placeholder="https://matrix.org",
                    id="homeserver",
                    classes="login-field",
                )
                yield Input(
                    placeholder="User ID (e.g. @you:matrix.org)",
                    id="user_id",
                    classes="login-field",
                )
                yield Input(
                    placeholder="Password",
                    password=True,
                    id="password",
                    classes="login-field",
                )
                yield Button("Sign in", id="login-button", variant="primary")
                yield Label("", id="login-status")
            yield Label(
                "Your credentials stay in ~/.config/matui (0600 permissions).",
                id="login-hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#homeserver", Input).focus()

    def _set_loading(self, loading: bool) -> None:
        button = self.query_one("#login-button", Button)
        button.disabled = loading
        button.label = "Connecting…" if loading else "Sign in"
        for field_id in ("homeserver", "user_id", "password"):
            self.query_one(f"#{field_id}", Input).disabled = loading

    def _set_status(self, message: str, *, kind: str = "") -> None:
        status = self.query_one("#login-status", Label)
        status.set_classes(kind)
        status.update(message)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._do_login()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-button":
            await self._do_login()

    async def _do_login(self) -> None:
        homeserver = self.query_one("#homeserver", Input).value.strip()
        user_id = self.query_one("#user_id", Input).value.strip()
        password = self.query_one("#password", Input).value

        if not (homeserver and user_id and password):
            self._set_status("Fill in all the fields.", kind="error")
            return

        self._set_status("")
        self._set_loading(True)
        try:
            creds = await NerveClient.login(homeserver, user_id, password)
        except Exception as exc:  # noqa: BLE001 — on affiche l'erreur à l'écran
            self._set_status(f"Connection failed: {exc}", kind="error")
            self._set_loading(False)
            return

        self._set_status("Connected, opening the chat…", kind="success")
        creds.save()
        app: NerveApp = self.app  # type: ignore[assignment]
        await app.start_chat(creds)