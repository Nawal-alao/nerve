"""Écran de sélection de compte (multi-account).

Affiche la liste des comptes sauvegardés et permet :
- de se connecter avec un compte existant
- d'ajouter un nouveau compte
- de supprimer un compte de la liste
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, ListItem, ListView, Rule, Static

from ..accounts import AccountInfo, get_manager
from ..matrix_client import NeuriteClient
from .login import LoginScreen


class AccountPickerScreen(Screen):
    """Écran de sélection parmi les comptes sauvegardés."""

    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("n", "new_account", "New"),
        ("d", "delete_account", "Delete"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="login-wrap"):
            with Vertical(id="login-card"):
                yield Static("◆ neurite", id="brand")
                yield Static(
                    "Choose an account to sign in.",
                    id="tagline",
                )
                yield Rule(classes="divider")
                yield Label("[dim]Saved accounts[/dim]", id="accounts-header")
                yield ListView(id="account-list", classes="account-list")
                yield Horizontal(
                    Button("New account", id="btn-new", classes="login-field"),
                    Button("Remove", id="btn-delete", classes="login-field"),
                    id="account-actions",
                )
            yield Label(
                "enter: select  ·  n: new account  ·  d: remove  ·  esc: quit",
                id="login-hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_accounts()

    def _refresh_accounts(self) -> None:
        manager = get_manager()
        lst = self.query_one("#account-list", ListView)
        lst.clear()
        for acc in manager.accounts:
            item = ListItem(
                Label(f"[bold]{acc.label}[/bold]\n[dim]{acc.user_id}[/dim]"),
            )
            item.data_user_id = acc.user_id  # type: ignore[attr-defined]
            lst.append(item)
        if manager.count() > 0:
            lst.index = 0

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        user_id = getattr(event.item, "data_user_id", None)
        if user_id:
            await self._sign_in(user_id)

    async def on_key(self, event) -> None:
        if event.key == "enter":
            lst = self.query_one("#account-list", ListView)
            if lst.highlighted_child is not None:
                user_id = getattr(lst.highlighted_child, "data_user_id", None)
                if user_id:
                    await self._sign_in(user_id)
                    event.stop()

    async def _sign_in(self, user_id: str) -> None:
        manager = get_manager()
        creds = manager.load_credentials(user_id)
        if creds is None or not creds.access_token:
            self.app.notify(
                "Could not load credentials. Please log in again.",
                severity="error",
            )
            return
        # Sauvegarder aussi dans credentials.json pour compatibilité
        creds.save()
        await self.app.start_chat(creds)

    def action_new_account(self) -> None:
        self.app.push_screen(LoginScreen())

    def action_delete_account(self) -> None:
        lst = self.query_one("#account-list", ListView)
        child = lst.highlighted_child
        if child is None:
            return
        user_id = getattr(child, "data_user_id", None)
        if user_id is None:
            return
        manager = get_manager()
        manager.remove(user_id)
        self._refresh_accounts()
        self.app.notify("Account removed from list")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self.action_new_account()
        elif event.button.id == "btn-delete":
            self.action_delete_account()
