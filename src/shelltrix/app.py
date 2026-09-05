"""Interface Textual de shelltrix.

Ce module assemble l'application : `ShelltrixApp` (app Textual principale) et
le point d'entrée `run()`. Les écrans, dialogues et helpers ont été extraits
en modules à part (screens/, dialogs/, formatting.py, sidebar.py,
widgets.py) — voir NOTES.md pour le détail du découpage.
"""

from __future__ import annotations

import argparse
from typing import Sequence

from textual.app import App

from . import __version__, themes
from .accounts import get_manager
from .config import Credentials, StoreLockedError, skip_splash
from .dialogs.command_palette import CommandPalette
from .dialogs.store_unlock import StoreUnlockDialog
from .matrix_client import ShelltrixClient
from .screens.account_picker import AccountPickerScreen
from .screens.chat import ChatScreen
from .screens.login import LoginScreen
from .screens.splash import SplashScreen

# Les couleurs markup (ACCENT/DANGER) suivent le thème actif : elles sont
# re-évaluées à chaque bascule de thème par _apply_theme_globals().
# Après le découpage en modules, les consommateurs lisent themes.accent()
# et themes.danger() directement (cf. NOTES.md). Les globals restent ici
# maintenues par ShelltrixApp mais n'ont plus d'utilisation.
ACCENT = "a2d399"
DANGER = "ffb4ab"


def _apply_theme_globals() -> None:
    """Repointe les constantes markup (ACCENT/DANGER) sur le thème actif."""
    global ACCENT, DANGER
    ACCENT = themes.accent()
    DANGER = themes.danger()


_apply_theme_globals()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ShelltrixApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "shelltrix"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [("ctrl+p", "command_palette", "Commands")]

    def __init__(self) -> None:
        super().__init__()
        # Les thèmes sont enregistrés AVANT le premier montage : les variables
        # CSS ($bg, $primary, ...) doivent exister quand app.tcss est compilé.
        themes.activate(self)
        _apply_theme_globals()

    def cycle_theme(self) -> str:
        """Bascule au thème suivant et persiste le choix."""
        name = themes.cycle(self.theme)
        self.theme = name
        themes.tick(name)
        themes.save_pref(name)
        _apply_theme_globals()
        self.notify(f"Theme: [bold]{themes.label(name)}[/bold]", title="Theme")
        return name

    async def on_mount(self) -> None:
        if skip_splash():
            await self.begin()
        else:
            await self.push_screen(SplashScreen())

    async def begin(self) -> None:
        """Après le splash : login ou reprise du chat selon les creds."""
        manager = get_manager()
        # Si plusieurs comptes sont enregistrés, proposer le sélecteur
        if manager.count() > 1:
            await self.push_screen(AccountPickerScreen())
            return
        creds = Credentials.load()
        if creds is None:
            await self.push_screen(LoginScreen())
        else:
            await self.start_chat(creds)

    def action_command_palette(self) -> None:
        self.push_screen(CommandPalette())

    # Les raccourcis natifs de bascule de thème de Textual permutent nos thèmes.
    def action_change_theme(self) -> None:
        self.cycle_theme()

    def action_search_themes(self) -> None:
        self.cycle_theme()

    async def start_chat(self, creds: Credentials) -> None:
        client = ShelltrixClient(creds=creds)
        try:
            client.load_local_store()
        except StoreLockedError:
            await self.push_screen(StoreUnlockDialog(creds, client))
            return
        await self.push_screen(ChatScreen(client))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shelltrix",
        description="shelltrix — un client Matrix TUI premium en Python "
        "(matrix-nio + Textual).",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"shelltrix {__version__}",
        help="show the version and exit",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> None:
    # `--version`/`-V`/`--help` sont gérés par argparse (action="version"
    # imprime et sort, sans lancer l'app Textual).
    _build_parser().parse_args(argv)
    ShelltrixApp().run()


if __name__ == "__main__":
    run()