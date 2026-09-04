"""Recherche dans l'historique local (messages en cache).

Modal `SearchDialog` : on tape un mot-clé et on obtient une liste de
correspondances parcourables (tous salons confondus). Sélectionner un
résultat ouvre le salon correspondant et positionne la timeline sur le
message. La recherche porte sur le cache SQLite local (`MessageCache`), donc
uniquement sur les messages déjà téléchargés.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from .. import themes

if TYPE_CHECKING:
    from ..screens.chat import ChatScreen


class SearchDialog(ModalScreen[None]):
    """Recherche locale de messages avec navigation vers le résultat."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("up", "prev", "Previous"),
        ("down,ctrl+n", "next", "Next"),
        ("ctrl+p", "prev", "Previous"),
    ]

    def __init__(self, chat: ChatScreen, initial_query: str = "") -> None:
        super().__init__()
        self.chat = chat
        self._hits: list[tuple[str, str]] = []  # (room_id, event_id)
        self.initial_query = initial_query or ""

    def compose(self) -> ComposeResult:
        with Vertical(id="cp-dialog"):
            with Horizontal(id="cp-search"):
                yield Static("⌕", id="cp-search-icon")
                yield Input(
                    placeholder="Search messages…",
                    id="cp-input",
                    value=self.initial_query,
                )
            yield ListView(id="cp-list")
            yield Static("No message found", id="cp-empty")

    async def on_mount(self) -> None:
        self.query_one("#cp-input", Input).focus()
        self._pop_lock = asyncio.Lock()
        await self._populate()
        input_widget = self.query_one("#cp-input", Input)
        input_widget.cursor_position = len(input_widget.value)

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "cp-input":
            await self._populate()

    def _query(self) -> str:
        return self.query_one("#cp-input", Input).value.strip()

    def _room_name(self, room_id: str) -> str:
        room = self.chat.client.rooms().get(room_id)
        return (room.display_name or room_id) if room else room_id

    @staticmethod
    def _markup(room_name: str, snippet: str, time: str) -> tuple[Text, Text]:
        muted = themes.muted()

        title = Text(room_name, style="bold")
        if snippet:
            title.append("  ·  ")
            title.append(snippet)
            title.stylize(muted, start=len(room_name) + 4, end=len(title.plain))

        right = Text(time, style=muted)
        return title, right

    @staticmethod
    def _build_row(room_name: str, snippet: str, time: str) -> ListItem:
        title, right = SearchDialog._markup(room_name, snippet, time)
        return ListItem(
            Horizontal(
                Label(title, classes="cp-row-title"),
                Static(right, classes="cp-row-right"),
                classes="cp-row",
            )
        )

    def _fit_list(self) -> None:
        lv = self.query_one("#cp-list", ListView)
        if lv.styles.display == "none" or not lv.children:
            return
        rows = len(lv.children)
        max_rows = max(3, int(self.size.height * 0.7) - 7)
        lv.styles.height = min(rows, max_rows)

    async def _populate(self) -> None:
        async with self._pop_lock:
            lv = self.query_one("#cp-list", ListView)
            empty = self.query_one("#cp-empty", Static)
            q = self._query()
            matches = self.chat._cache.search_with_room(q, limit=200)
            if not matches:
                empty.update(
                    f"No message found for “{q}”" if q else "Type to search"
                )
                await lv.clear()
                empty.styles.display = "block"
                lv.styles.display = "none"
                return
            empty.styles.display = "none"
            lv.styles.display = "block"
            await lv.clear()
            self._hits = []
            for room_id, entry in matches:
                snippet = " ".join(entry.body.split())
                item = self._build_row(self._room_name(room_id), snippet, entry.timestamp)
                item.data_room_id = room_id  # type: ignore[attr-defined]
                item.data_event_id = entry.event_id  # type: ignore[attr-defined]
                self._hits.append((room_id, entry.event_id))
                await lv.append(item)
            if lv.children:
                lv.index = 0
            self._fit_list()

    def _selected_item(self) -> ListItem | None:
        lv = self.query_one("#cp-list", ListView)
        return lv.highlighted_child

    def _move(self, direction: int) -> None:
        lv = self.query_one("#cp-list", ListView)
        n = len(lv.children)
        if n == 0:
            return
        idx = 0 if lv.index is None else lv.index
        lv.index = (idx + direction) % n

    def action_next(self) -> None:
        self._move(1)

    def action_prev(self) -> None:
        self._move(-1)

    def _navigate(self, item: ListItem | None) -> None:
        room_id = getattr(item, "data_room_id", None)
        event_id = getattr(item, "data_event_id", None)
        if room_id is None or not event_id:
            return
        self.dismiss()
        self.app.call_after_refresh(lambda: self.chat.open_message(room_id, event_id))

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._navigate(event.item)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cp-input":
            self._navigate(self._selected_item())
