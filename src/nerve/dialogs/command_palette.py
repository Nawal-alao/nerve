"""Palette de commandes (ctrl+p) — collage ultra-plat, façon opencode.

Contient le registre de commandes `COMMANDS`, l'ordre des sections et
l'écran modal `CommandPalette`. Extrait de `app.py`.
"""

from __future__ import annotations

import asyncio
from typing import NamedTuple

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from .. import themes
from ..screens.chat import ChatScreen
from .join_room import JoinRoomDialog
from .recovery import RecoveryDialog


class CommandEntry(NamedTuple):
    id: str
    title: str
    description: str
    key: str
    category: str
    suggested: bool = False


COMMANDS: list[CommandEntry] = [
    CommandEntry(
        "focus_rooms",
        "Focus rooms",
        "Jump to the rooms list",
        "ctrl+r",
        "Navigation",
        suggested=True,
    ),
    CommandEntry(
        "focus_input",
        "Write a message",
        "Focus the message input",
        "ctrl+l",
        "Navigation",
        suggested=True,
    ),
    CommandEntry(
        "toggle_sidebar",
        "Toggle sidebar",
        "Show or hide the right context panel",
        "ctrl+d",
        "Navigation",
    ),
    CommandEntry(
        "clear_screen",
        "Clear screen",
        "Clear the active room timeline",
        "ctrl+k",
        "Chat",
    ),
    CommandEntry(
        "mark_read",
        "Mark as read",
        "Reset the unread counter",
        "",
        "Chat",
    ),
    CommandEntry(
        "join_room",
        "Join a room",
        "Type an alias (#room:server)",
        "",
        "Chat",
    ),
    CommandEntry(
        "sendimg",
        "Send an image",
        "Insert /sendimg in the composer",
        "",
        "Action",
    ),
    CommandEntry(
        "open_last_link",
        "Open last link",
        "Open the recent URL of the active room",
        "",
        "Action",
    ),
    CommandEntry(
        "sync_status",
        "Sync status",
        "Show the current sync state",
        "",
        "System",
    ),
    CommandEntry(
        "theme",
        "Switch theme",
        "Toggle between OpenCode Zen and Matrix Green",
        "",
        "System",
    ),
    CommandEntry(
        "recovery",
        "Recovery key",
        "Show or regenerate the E2EE session recovery key",
        "",
        "System",
    ),
    CommandEntry(
        "logout",
        "Sign out",
        "Close the session and erase local data",
        "",
        "System",
    ),
    CommandEntry(
        "quit",
        "Quit nerve",
        "Close the application",
        "ctrl+q",
        "System",
    ),
]


# Ordre des sections (en-têtes non sélectionnables) dans la vue groupée.
SECTIONS = ("Suggested", "Navigation", "Chat", "Action", "System")


class CommandPalette(ModalScreen[None]):
    """Palette de commandes façon opencode (ctrl+p) : collage ultra-plat."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("up", "prev", "Previous"),
        ("down,ctrl+n", "next", "Next"),
        ("ctrl+p", "prev", "Previous"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="cp-dialog"):
            with Horizontal(id="cp-title"):
                yield Static("Commands", id="cp-title-text")
                yield Static("esc", id="cp-title-esc")
            with Horizontal(id="cp-search"):
                yield Static("⌕", id="cp-search-icon")
                yield Input(placeholder="Search commands…", id="cp-input")
            yield ListView(id="cp-list")
            yield Static("No command found", id="cp-empty")

    async def on_mount(self) -> None:
        self.query_one("#cp-input", Input).focus()
        self._rows: list[CommandEntry | str] = []
        self._pop_lock = asyncio.Lock()
        await self._populate()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "cp-input":
            await self._populate()

    def _query(self) -> str:
        return self.query_one("#cp-input", Input).value.strip().lower()

    @staticmethod
    def _markup(entry: CommandEntry, cursor: bool) -> tuple[Text, Text]:
        # Segments stylés via rich.text.Text uniquement : n'utilisent aucun
        # markup d'échappement, le raccourci et la description sont bruts.
        if cursor:
            color = themes.accent_text()
            title = Text(entry.title, style=f"bold {color}")
        else:
            title = Text(entry.title)
        right = Text()
        if entry.key:
            right.append(entry.key)
            right.stylize(
                f"bold {themes.accent_text()}" if cursor else themes.muted()
            )
        elif entry.description:
            right.append(entry.description)
            right.stylize(themes.muted())
        return title, right

    @staticmethod
    def _build_row(entry: CommandEntry) -> ListItem:
        title, right = CommandPalette._markup(entry, False)
        return ListItem(
            Horizontal(
                Label(title, classes="cp-row-title"),
                Static(right, classes="cp-row-right"),
                classes="cp-row",
            )
        )

    @staticmethod
    def _build_header(section: str) -> ListItem:
        return ListItem(Label(f"  {section}", classes="cp-section"))

    def _matching(self, q: str) -> list[CommandEntry]:
        return [
            c
            for c in COMMANDS
            if (not q or q in c.title.lower() or q in c.description.lower())
        ]

    def _grouped(self, commands: list[CommandEntry]) -> list[CommandEntry | str]:
        rows: list[CommandEntry | str] = []
        for section in SECTIONS:
            members = [
                c
                for c in commands
                if (section == "Suggested" and c.suggested)
                or (section == c.category and not c.suggested)
            ]
            members.sort(key=lambda c: c.title)
            if members:
                if rows:  # respiration entre les sections (sauf la première)
                    rows.append("")
                rows.append(section)  # en-tête de section
                rows.extend(members)
        remaining = [c for c in commands if c.category not in SECTIONS]
        if remaining and rows:
            rows.append("")
        rows.extend(sorted(remaining, key=lambda c: (c.category, c.title)))
        return rows

    def _first_command_index(self) -> int:
        for i, entry in enumerate(self._rows):
            if isinstance(entry, CommandEntry):
                return i
        return 0

    def _fit_list(self) -> None:
        lv = self.query_one("#cp-list", ListView)
        if lv.styles.display == "none" or not lv.children:
            return
        # Le dialogue est plafonné à 70% de l'écran : on borne la liste à ce
        # qui tient dedans (sinon elle déborde sous le dialogue) et on la
        # laisse au plus haut de son contenu (pas de vide en dessous).
        rows = len(lv.children)
        max_rows = max(3, int(self.size.height * 0.7) - 7)
        lv.styles.height = min(rows, max_rows)

    async def _populate(self) -> None:
        # Les frappes rapides lancent des _populate concurrents (Input.Changed
        # pendant un clear/append). Un verrou les sérialise : _rows et les
        # enfants de la liste restent cohérents, sinon _move pouvait indexer
        # hors bornes avec un contenu partiellement remplacé.
        async with self._pop_lock:
            q = self._query()
            if q:
                self._rows = list(self._matching(q))
            else:
                self._rows = self._grouped(self._matching(""))
            lv = self.query_one("#cp-list", ListView)
            empty = self.query_one("#cp-empty", Static)
            if not any(self._rows):
                empty.update(
                    f"No command found for “{q}”" if q else "No command found"
                )
                await lv.clear()
                empty.styles.display = "block"
                lv.styles.display = "none"
                return
            empty.styles.display = "none"
            lv.styles.display = "block"
            await lv.clear()
            for entry in self._rows:
                if isinstance(entry, str):
                    await lv.append(self._build_header(entry))
                else:
                    item = self._build_row(entry)
                    item.data_id = entry.id  # type: ignore[attr-defined]
                    await lv.append(item)
            lv.index = self._first_command_index()
            self._fit_list()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        lv = event.list_view
        if lv.id != "cp-list" or not self._rows:
            return
        idx = lv.index if lv.index is not None else 0
        for i, (child, entry) in enumerate(zip(lv.children, self._rows)):
            if not isinstance(entry, CommandEntry):
                continue
            try:
                title, right = self._markup(entry, i == idx)
                child.query_one(".cp-row-title", Label).update(title)
                child.query_one(".cp-row-right", Static).update(right)
            except Exception:
                pass

    def _selected_id(self) -> str | None:
        lv = self.query_one("#cp-list", ListView)
        child = lv.highlighted_child
        return getattr(child, "data_id", None) if child is not None else None

    def _move(self, direction: int) -> None:
        lv = self.query_one("#cp-list", ListView)
        n = len(lv.children)
        if n == 0:
            return
        idx = 0 if lv.index is None else lv.index
        step = 0
        while step < n:
            idx = (idx + direction) % n
            step += 1
            if isinstance(self._rows[idx], CommandEntry):
                break
        lv.index = idx

    def action_next(self) -> None:
        self._move(1)

    def action_prev(self) -> None:
        self._move(-1)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        cmd_id = getattr(event.item, "data_id", None)
        if cmd_id is not None:
            await self._run(cmd_id)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cp-input":
            cmd_id = self._selected_id()
            if cmd_id is not None:
                await self._run(cmd_id)

    async def _run(self, cmd_id: str) -> None:
        self.dismiss()

        async def _go() -> None:
            app = self.app
            if cmd_id == "quit":
                app.exit()
                return
            if cmd_id == "theme":
                app.cycle_theme()  # type: ignore[attr-defined]
                return
            chat = next(
                (
                    s
                    for s in reversed(app.screen_stack)
                    if isinstance(s, ChatScreen)
                ),
                None,
            )
            if chat is None:
                app.notify("This command is available in the chat")
                return
            if cmd_id == "focus_rooms":
                chat.action_focus_rooms()
            elif cmd_id == "focus_input":
                chat.action_focus_input()
            elif cmd_id == "toggle_sidebar":
                chat.action_toggle_sidebar()
            elif cmd_id == "clear_screen":
                chat.action_clear_screen()
            elif cmd_id == "mark_read":
                chat.action_mark_read()
            elif cmd_id == "open_last_link":
                chat.action_open_last_link()
            elif cmd_id == "sync_status":
                chat.action_sync_status()
            elif cmd_id == "sendimg":
                chat.action_insert_slash("/sendimg ")
            elif cmd_id == "join_room":
                await app.push_screen(JoinRoomDialog(chat))
            elif cmd_id == "recovery":
                await app.push_screen(RecoveryDialog(chat))
            elif cmd_id == "logout":
                # Changer d'écran à l'intérieur d'un callback awaité bloque
                # (attente du close du screen courant depuis son propre pump).
                # On le détache donc dans une tâche indépendante.
                asyncio.create_task(chat.logout_and_return_to_login())

        # La fermeture du modal est asynchrone : on diffère l'exécution
        # pour que le focus se pose sur l'écran de chat après le retrait.
        # Le callback est de toute façon awaité par la file d'appels du screen.
        self.app.call_after_refresh(_go)