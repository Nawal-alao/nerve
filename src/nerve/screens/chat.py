"""Écran principal du chat : salons à gauche, timeline + saisie à droite."""

from __future__ import annotations

import asyncio
import time
import webbrowser

from nio import MatrixRoom, RoomMessageImage, RoomMessageText
from rich.markup import escape
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, Input, Label, ListItem, ListView, RichLog, Static

from .. import themes
from ..config import recovery_has_verifier
from ..dialogs.invite import InviteDialog
from ..dialogs.recovery import RecoveryDialog
from ..dialogs.sas import SasDialog
from ..formatting import (
    _URL_RE,
    _format_time,
    _fuzzy_score,
    _inline_markdown,
    _sender_color,
)
from ..image_renderer import format_image_message, is_image_message, render_image
from ..matrix_client import NerveClient
from ..notifications import notify
from ..sidebar import _sidebar_room_markup, _sidebar_session_markup
from ..widgets import _SendButton
from .login import LoginScreen

# Correspondance état de sync → (libellé, couleur) pour le header. Les
# couleurs sont des constantes figées (non reliées au thème) ; seule la
# ligne "online" bascule sur themes.accent() à l'affichage.
SYNC_LABELS = {
    "connecting": ("offline", "#ff6f6f"),
    "syncing": ("syncing…", "#d7a85f"),
    "online": ("online", "#88c285"),
    "offline": ("off-line", "#ff6f6f"),
    "reconnecting": ("reconnecting…", "#d7a85f"),
}


class ChatScreen(Screen):
    """L'interface principale : salons à gauche, timeline + saisie à droite."""

    BINDINGS = [
        ("ctrl+r", "focus_rooms", "Rooms"),
        ("ctrl+l", "focus_input", "Compose"),
        ("ctrl+k", "clear_screen", "Clear"),
        ("ctrl+d", "toggle_sidebar", "Sidebar"),
    ]

    def __init__(self, client: NerveClient) -> None:
        super().__init__()
        self.client = client
        self.active_room_id: str | None = None
        self.unread: dict[str, int] = {}
        self.message_log: dict[str, list[str]] = {}
        # Dernier event_id reçu par salon : sert à la commande /react.
        self.last_event_id: dict[str, str] = {}
        # Dernière URL aperçue par salon : sert à la commande "ouvrir le lien".
        self.last_link: dict[str, str] = {}
        # Autocomplétion des slash commands (liste floue sous le composer).
        self._suggestions_active = False
        self._suggestion_index = 0
        self._suggestion_commands: list[str] = []
        # Autocomplétion des mentions @username / #room.
        self._mention_active = False
        self._mention_index = 0
        self._mention_type: str | None = None  # "user" ou "room"
        self._mention_query: str = ""
        self._mention_start: int = 0
        self._mention_items: list[tuple[str, str]] = []  # (affichage, à insérer)
        # Jeton de sync observé (sidebar SESSION) : heure (wall) du dernier
        # changement de next_batch, pour afficher "Refresh Xs ago".
        self._last_nb: str | None = None
        self._nb_time: float | None = None
        # Timer du statut (sync/clock) — stocké pour nettoyage sur unmount.
        self._status_timer: Timer | None = None
        # Indicateurs de typing (server-authoritative : chaque événement
        # contient la liste COMPLÈTE des utilisateurs en train de taper).
        self._typing_users: dict[str, set[str]] = {}
        self._typing_last_seen: dict[str, float] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Static("No room selected", id="room-title")
            yield Static("● offline", id="sync-status")
            yield Static("", id="clock")
        with Horizontal(id="main"):
            with Vertical(id="room-panel"):
                yield Static("◆ nerve", id="brand-sidebar")
                yield Static("ROOMS", id="room-list-header")
                yield ListView(id="room-list")
            with Vertical(id="chat-area"):
                yield RichLog(id="timeline", wrap=True, highlight=True, markup=True)
                yield ListView(id="suggestion-list")
                yield Static("", id="typing-status")
                with Horizontal(id="input-bar"):
                    yield Static(">", id="input-prompt")
                    yield Input(
                        placeholder="Select a room to chat",
                        id="composer",
                        disabled=True,
                    )
                    yield _SendButton("→", id="composer-send")
            with Vertical(id="sidebar"):
                yield Static("", id="sb-room")
                yield Static("", id="sb-session")
        yield Footer()

    async def on_mount(self) -> None:
        self.client.on_message = self._handle_incoming_message
        self.client.on_image = self._handle_incoming_image
        self.client.on_typing = self._handle_typing
        self.client.on_invite = self._show_invite_dialog
        self.client.on_sas_request = self._show_sas_dialog
        self.client.on_send_error = self._on_send_error
        self._status_timer = self.set_interval(1.0, self._tick_status)
        self._tick_status()  # "syncing…" during the first sync
        await self.client.start()
        self._refresh_room_list()
        timeline = self.query_one("#timeline", RichLog)
        timeline.write(
            "\n[dim]· · ·  Pick a room from the list to start chatting  · · ·[/dim]"
        )

    def on_unmount(self) -> None:
        """Arrête le timer de statut pour éviter un leak."""
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None

    def _set_composer_enabled(self, enabled: bool) -> None:
        """Verrouille/active la saisie selon qu'un salon est ouvert ou non."""
        composer = self.query_one("#composer", Input)
        composer.disabled = not enabled
        # Espace initial : quand l'input est vide et focusé, le curseur (bloc)
        # se rend sur cette espace et non pas sur le premier caractère du
        # placeholder — évite le glitch visuel "Iype a message…".
        composer.placeholder = " Type a message…" if enabled else "Select a room to chat"
        if not enabled:
            composer.value = ""
            if self._suggestions_active:
                self._hide_suggestions()
            if self._mention_active:
                self._hide_mention_suggestions()
        else:
            self._update_suggestions(composer.value)
        # Premier appareil sans clé de récupération : on invite à la créer pour
        # pouvoir restaurer la session (clés E2EE) sur une autre machine.
        if not recovery_has_verifier():
            self.app.notify(
                "Run /recovery to back up your session recovery key",
                title="Encryption",
            )

    async def _show_sas_dialog(
        self,
        transaction_id: str,
        user_id: str,
        device_id: str,
        emojis: list[tuple[str, str]],
    ) -> None:
        await self.app.push_screen(
            SasDialog(self.client, transaction_id, user_id, device_id, emojis)
        )

    def _tick_status(self) -> None:
        accent = themes.accent()
        label, color = SYNC_LABELS.get(
            self.client.sync_state, ("idle", themes.muted())
        )
        if self.client.sync_state == "online":
            color = accent
        self.query_one("#sync-status", Static).update(f"[{color}]●[/{color}] {label}")
        self.query_one("#clock", Static).update(time.strftime("%H:%M"))
        self._refresh_sidebar()
        self._purge_typing()

    def _purge_typing(self) -> None:
        """Nettoie les typing expirés (filet de sécurité, 5s sans événement)."""
        now = time.monotonic()
        expired = [
            rid
            for rid, last_seen in self._typing_last_seen.items()
            if now - last_seen > 5.0
        ]
        for rid in expired:
            self._typing_users.pop(rid, None)
            self._typing_last_seen.pop(rid, None)
        if expired and self.active_room_id in expired:
            self._refresh_typing_display()

    async def _handle_typing(self, room_id: str, user_ids: list[str]) -> None:
        """Gère un événement typing (server-authoritative, liste complète)."""
        own_id = self.client.client.user_id
        typing = {uid for uid in user_ids if uid != own_id}
        self._typing_users[room_id] = typing
        self._typing_last_seen[room_id] = time.monotonic()
        if room_id == self.active_room_id:
            self._refresh_typing_display()

    def _refresh_typing_display(self) -> None:
        """Met à jour le widget de typing pour la room active."""
        typing = self._typing_users.get(self.active_room_id, set())
        widget = self.query_one("#typing-status", Static)
        if not typing:
            widget.update("")
            widget.styles.display = "none"
            return
        names = []
        rooms = self.client.rooms()
        room = rooms.get(self.active_room_id)
        for uid in typing:
            if room is not None:
                name = room.user_name(uid) or uid
            else:
                name = uid
            names.append(name)
        if len(names) == 1:
            text = f"{names[0]} is typing…"
        elif len(names) == 2:
            text = f"{names[0]} and {names[1]} are typing…"
        else:
            text = f"{len(names)} people are typing…"
        widget.update(f"[dim]{escape(text)}[/dim]")
        widget.styles.display = "block"

    def _refresh_sidebar(self) -> None:
        """Re-synthetise les deux panneaux contextuels (Room / Session)."""
        room = None
        if self.active_room_id:
            room = self.client.rooms().get(self.active_room_id)
        own_id = getattr(getattr(self.client, "client", None), "user_id", None) or ""
        self.query_one("#sb-room", Static).update(
            _sidebar_room_markup(room, own_id)
        )
        nb = getattr(self.client.client, "next_batch", None)
        nb = nb if isinstance(nb, str) else None
        now = time.time()
        if nb:
            if nb != self._last_nb:
                self._last_nb = nb
                self._nb_time = now
        self.query_one("#sb-session", Static).update(
            _sidebar_session_markup(self.client.sync_state, nb, self._nb_time, now)
        )

    def action_toggle_sidebar(self) -> None:
        self.query_one("#sidebar").display = not self.query_one("#sidebar").display

    def _refresh_room_list(self) -> None:
        room_list = self.query_one("#room-list", ListView)
        room_list.clear()
        accent = themes.accent()
        ordered = sorted(
            self.client.rooms().items(),
            key=lambda kv: (
                self.unread.get(kv[0], 0) == 0,  # les salons non-lus d'abord
                (kv[1].display_name or kv[0]).lower(),
            ),
        )
        for room_id, room in ordered:
            name = room.display_name or room_id
            unread = self.unread.get(room_id, 0)
            is_active = room_id == self.active_room_id
            if unread and not is_active:
                name_label = Label(
                    f"[bold][{accent}]{escape(name)}[/{accent}][/bold]",
                    classes="room-name",
                )
            else:
                name_label = Label(escape(name), classes="room-name")
            if unread:
                row = Horizontal(
                    name_label,
                    Label(str(unread), classes="room-badge"),
                    classes="room-row",
                )
            else:
                row = Horizontal(name_label, classes="room-row")
            item = ListItem(row)
            item.data_room_id = room_id  # type: ignore[attr-defined]
            if is_active:
                item.add_class("active")
            room_list.append(item)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        room_id = getattr(event.item, "data_room_id", None)
        if room_id is None:
            return
        self.active_room_id = room_id
        self.unread[room_id] = 0
        room = self.client.rooms().get(room_id)
        title = (room.display_name or room_id) if room else room_id
        self.query_one("#room-title", Static).update(f"[bold]{escape(title)}[/bold]")
        self._refresh_room_list()
        timeline = self.query_one("#timeline", RichLog)
        timeline.clear()
        for line in self.message_log.get(room_id, []):
            timeline.write(line)
        self._refresh_sidebar()
        self._refresh_typing_display()
        self._set_composer_enabled(True)
        self.query_one("#composer", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        """Largeurs progressives des sidebars selon la largeur du terminal.

        Grille visée à 1920×1080 (~210 colonnes) : ~30 cellules de chaque
        côté, le chat prend tout le reste. En dessous, on réduit de paliers
        pour ne jamais saturer l'écran ; sous 100 colonnes on masque la
        sidebar droite (toujours remplaçable par le raccourci existant).
        """
        w = event.size.width
        if w >= 200:
            left = right = 30
        elif w >= 150:
            left = right = 26
        elif w >= 110:
            left = right = 22
        else:
            left = right = 20
        try:
            self.query_one("#room-panel").styles.width = left
            sb = self.query_one("#sidebar")
            sb.styles.width = right
            sb.display = sb.display if w >= 100 else False
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "composer" or self.active_room_id is None:
            return
        await self._dispatch_compose(event.input)

    async def _dispatch_compose(self, composer: Input) -> None:
        # Entrée pendant que l'autocomplétion est ouverte : on complète la
        # commande surlignée au lieu d'exécuter la saisie.
        if self._suggestions_active:
            self._accept_suggestion()
            return
        if self._mention_active:
            self._accept_mention_suggestion()
            return
        body = composer.value.strip()
        if not body:
            return
        composer.value = ""
        if body.startswith("/"):
            await self._run_slash_command(self.active_room_id, body)
            return
        await self.client.send_message(self.active_room_id, body)

    # ------------------------------------------------------------------
    # Commandes slash
    # ------------------------------------------------------------------
    SLASH_HELP = {
        "/me <text>": "send an action (m.emote, rendered in italic)",
        "/react <emoji>": "react to the last received message",
        "/join <#alias>": "join a room by alias",
        "/sendimg <path>": "send an image from disk",
        "/quit [farewell]": "leave the room (optional farewell message)",
        "/recovery": "show or regenerate the E2EE session recovery key",
        "/theme": "switch theme (OpenCode Zen / Matrix Green)",
        "/help": "show this help",
    }
    # Commandes canoniques (sans usage) pour la complétion fuzzy.
    SLASH_COMMANDS: list[str] = [usage.split()[0] for usage in SLASH_HELP]
    SLASH_DESC = {
        "/me": "send an action",
        "/react": "react to the last message",
        "/join": "join a room",
        "/sendimg": "send an image",
        "/quit": "leave the room",
        "/recovery": "session recovery key",
        "/theme": "switch theme",
        "/help": "show this help",
    }

    async def _run_slash_command(self, room_id: str, raw: str) -> None:
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            self._cmd_help()
        elif cmd == "/theme":
            self.app.cycle_theme()  # type: ignore[attr-defined]
        elif cmd == "/me":
            if not arg:
                self.app.notify("/me <text>: a text is required", severity="error")
                return
            await self.client.send_emote(room_id, arg)
        elif cmd == "/react":
            if not arg:
                self.app.notify("/react <emoji>: provide an emoji", severity="error")
                return
            event_id = self.last_event_id.get(room_id)
            if not event_id:
                self.app.notify("No message received to react to in this room")
                return
            await self.client.react_to(room_id, event_id, arg)
        elif cmd == "/join":
            if not arg or not arg.startswith("#"):
                self.app.notify("/join <#alias>: provide a room alias", severity="error")
                return
            await self.client.join_room(arg)
            await self._refresh_room_list_async()
        elif cmd == "/sendimg":
            if not arg:
                self.app.notify("/sendimg <path>: provide a file path", severity="error")
                return
            await self.client.send_image(room_id, arg)
        elif cmd == "/quit":
            await self.client.part_room(room_id, arg or None)
            self.active_room_id = None
            self.query_one("#room-title", Static).update(
                "[bold]No room selected[/bold]"
            )
            self._set_composer_enabled(False)
            self._refresh_room_list()
            self._refresh_sidebar()
        elif cmd == "/recovery":
            self.app.push_screen(RecoveryDialog(self))  # type: ignore[attr-defined]
        else:
            self.app.notify(
                f"Unknown command: {cmd} (type /help)",
                severity="error",
            )

    def _cmd_help(self) -> None:
        accent = themes.accent()
        lines = [f"[bold][{accent}]/{cmd}[/{accent}]  {desc}" for cmd, desc in self.SLASH_HELP.items()]
        self.app.notify(
            f"[bold]Slash commands[/bold]\n" + "\n".join(lines),
            title="Commands",
            timeout=8,
        )

    # ------------------------------------------------------------------
    # Autocomplétion fuzzy des slash commands
    # ------------------------------------------------------------------
    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "composer":
            cursor = event.input.cursor_position
            self._update_suggestions(event.value, cursor)

    def _matching_commands(self, query: str) -> list[str]:
        scored = [
            (score, cmd)
            for cmd in self.SLASH_COMMANDS
            if (score := _fuzzy_score(query, cmd[1:])) >= 0
        ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [cmd for _, cmd in scored]

    def _update_suggestions(self, value: str, cursor: int | None = None) -> None:
        """Met à jour les suggestions : slash commands ou mentions @/#."""
        if cursor is None:
            cursor = len(value)
        # D'abord vérifier les mentions @/# (priorité sur les slash commands)
        if not value.startswith("/"):
            self._suggestions_active = False
            self._update_mention_suggestions(value, cursor)
            return
        # Sinon, slash commands
        self._mention_active = False
        accent = themes.accent()
        lst = self.query_one("#suggestion-list", ListView)
        if not value.startswith("/"):
            self._hide_suggestions()
            return
        self._suggestion_commands = self._matching_commands(value[1:])
        if not self._suggestion_commands:
            self._hide_suggestions()
            return
        lst.clear()
        for cmd in self._suggestion_commands:
            desc = self.SLASH_DESC.get(cmd, "")
            item = ListItem(
                Label(
                    f"[bold][{accent}]{escape(cmd)}[/{accent}][/bold]"
                    f"  [dim]{escape(desc)}[/dim]"
                )
            )
            lst.append(item)
        self._suggestion_index = 0
        lst.index = 0
        self._suggestions_active = True
        lst.styles.display = "block"

    def _hide_suggestions(self) -> None:
        self._suggestions_active = False
        self._suggestion_commands = []
        if not self._mention_active:
            self.query_one("#suggestion-list", ListView).styles.display = "none"

    # ------------------------------------------------------------------
    # Autocomplétion des mentions @username / #room
    # ------------------------------------------------------------------
    def _active_room_users(self) -> list[tuple[str, str]]:
        """Liste des membres du salon actif : [(user_id, display_name)]."""
        if self.active_room_id is None:
            return []
        room = self.client.rooms().get(self.active_room_id)
        if room is None:
            return []
        users: list[tuple[str, str]] = []
        for uid in getattr(room, "users", {}):
            name = room.user_name(uid) or uid
            users.append((uid, name))
        users.sort(key=lambda t: t[1].lower())
        return users

    def _all_rooms(self) -> list[tuple[str, str]]:
        """Liste de tous les salons : [(alias_or_id, nom_affiché)]."""
        rooms: list[tuple[str, str]] = []
        for rid, room in self.client.rooms().items():
            alias = getattr(room, "canonical_alias", None)
            name = room.display_name or rid
            if alias:
                rooms.append((alias, name))
            else:
                rooms.append((rid, name))
        rooms.sort(key=lambda t: t[1].lower())
        return rooms

    def _find_mention_start(self, value: str, cursor: int) -> tuple[int, str, str] | None:
        """Détecte si le curseur est dans une mention @ ou #.

        Retourne (position_début, type, query) ou None.
        type = "user" pour @, "room" pour #.
        """
        if not value or cursor == 0:
            return None
        # Chercher le @ ou # le plus proche avant le curseur
        at_pos = value.rfind("@", 0, cursor)
        hash_pos = value.rfind("#", 0, cursor)
        pos = max(at_pos, hash_pos)
        if pos == -1:
            return None
        # Vérifier que la mention est en début de mot (début de chaîne ou précédé d'un espace)
        if pos > 0 and value[pos - 1] != " ":
            return None
        # Extraire la query (sans @ ou #)
        mention = value[pos:cursor]
        if not mention:
            return None
        prefix = mention[0]
        query = mention[1:]
        # Ne proposer que si la query ne contient pas d'espace (mention en cours)
        if " " in query:
            return None
        mtype = "user" if prefix == "@" else "room"
        return (pos, mtype, query)

    def _update_mention_suggestions(self, value: str, cursor: int) -> None:
        """Met à jour la liste des suggestions de mention."""
        found = self._find_mention_start(value, cursor)
        if found is None:
            self._hide_mention_suggestions()
            return
        start, mtype, query = found
        self._mention_start = start
        self._mention_type = mtype
        self._mention_query = query

        if mtype == "user":
            candidates = self._active_room_users()
        else:
            candidates = self._all_rooms()

        # Filtrer par fuzzy match
        q = query.lower()
        scored: list[tuple[float, str, str]] = []
        for insert, display in candidates:
            score = _fuzzy_score(q, display.lower())
            if score >= 0:
                scored.append((score, display, insert))
        scored.sort(key=lambda t: -t[0])
        self._mention_items = [(d, i) for _, d, i in scored]

        if not self._mention_items:
            self._hide_mention_suggestions()
            return

        accent = themes.accent()
        lst = self.query_one("#suggestion-list", ListView)
        lst.clear()
        for display, insert in self._mention_items[:10]:  # max 10 résultats
            prefix = "@" if mtype == "user" else "#"
            item = ListItem(
                Label(
                    f"[bold][{accent}]{prefix}{escape(display)}[/{accent}][/bold]"
                    f"  [dim]{escape(insert)}[/dim]"
                )
            )
            lst.append(item)
        self._mention_index = 0
        lst.index = 0
        self._mention_active = True
        lst.styles.display = "block"

    def _hide_mention_suggestions(self) -> None:
        self._mention_active = False
        self._mention_items = []
        self._mention_type = None
        if not self._suggestions_active:
            self.query_one("#suggestion-list", ListView).styles.display = "none"

    def _accept_mention_suggestion(self) -> None:
        if not (0 <= self._mention_index < len(self._mention_items)):
            self._hide_mention_suggestions()
            return
        display, insert = self._mention_items[self._mention_index]
        composer = self.query_one("#composer", Input)
        value = composer.value
        # Remplacer la mention par le choix + espace
        end = self._mention_start + len(self._mention_query) + 1  # +1 pour @ ou #
        new_value = value[:self._mention_start] + insert + " " + value[end:]
        composer.value = new_value
        composer.cursor_position = self._mention_start + len(insert) + 1
        self._hide_mention_suggestions()
        composer.focus()

    def _accept_suggestion(self) -> None:
        commands = self._suggestion_commands
        if not (0 <= self._suggestion_index < len(commands)):
            self._hide_suggestions()
            return
        cmd = commands[self._suggestion_index]
        self._hide_suggestions()
        self._hide_mention_suggestions()
        composer = self.query_one("#composer", Input)
        composer.value = f"{cmd} "
        composer.cursor_position = len(composer.value)
        composer.focus()

    def on_key(self, event: events.Key) -> None:
        if self._mention_active:
            lst = self.query_one("#suggestion-list", ListView)
            total = len(self._mention_items)
            if event.key == "down":
                self._mention_index = min(self._mention_index + 1, total - 1)
                lst.index = self._mention_index
                event.stop()
            elif event.key == "up":
                self._mention_index = max(self._mention_index - 1, 0)
                lst.index = self._mention_index
                event.stop()
            elif event.key == "escape":
                self._hide_mention_suggestions()
                event.stop()
            return
        if not self._suggestions_active:
            return
        lst = self.query_one("#suggestion-list", ListView)
        total = len(self._suggestion_commands)
        if event.key == "down":
            self._suggestion_index = min(self._suggestion_index + 1, total - 1)
            lst.index = self._suggestion_index
            event.stop()
        elif event.key == "up":
            self._suggestion_index = max(self._suggestion_index - 1, 0)
            lst.index = self._suggestion_index
            event.stop()
        elif event.key == "escape":
            self._hide_suggestions()
            event.stop()

    async def _refresh_room_list_async(self) -> None:
        # Petite latence pour laisser au serveur le temps d'accepter le join
        # avant le prochain rafraîchissement.
        await asyncio.sleep(0.3)
        self._refresh_room_list()

    async def _handle_incoming_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        own = event.sender == self.client.client.user_id
        timestamp = _format_time(event.server_timestamp)
        body = _inline_markdown(event.body)
        # On mémorise le dernier event_id du salon : la commande /react s'y
        # réfère pour poser une réaction.
        self.last_event_id[room.room_id] = event.event_id
        # et la dernière URL aperçue, pour "ouvrir le dernier lien".
        m = _URL_RE.search(event.body)
        if m:
            self.last_link[room.room_id] = m.group(0)
        if own:
            accent = themes.accent()
            line = (
                f"[dim]{timestamp}[/dim] "
                f"[bold][{accent}]› Vous[/{accent}][/bold]  {body}"
            )
        else:
            name = escape(room.user_name(event.sender) or event.sender)
            color = _sender_color(event.sender)
            line = f"[dim]{timestamp}[/dim] [{color}]{name}[/{color}]  {body}"

        # On garde toujours le message en mémoire, qu'il arrive pendant
        # que le salon est actif ou non : il pourra être réaffiché à
        # l'ouverture du salon.
        self.message_log.setdefault(room.room_id, []).append(line)

        if room.room_id != self.active_room_id:
            self.unread[room.room_id] = self.unread.get(room.room_id, 0) + 1
            self._refresh_room_list()
            if not own:
                notify(
                    room.display_name or room.name or room_id,
                    room.user_name(event.sender) or event.sender,
                    event.body,
                )
            return
        self.query_one("#timeline", RichLog).write(line)

    async def _handle_incoming_image(
        self, room: MatrixRoom, event: "RoomMessageImage"
    ) -> None:
        """Gère la réception d'une image."""
        from nio import RoomMessageImage

        own = event.sender == self.client.client.user_id
        timestamp = _format_time(event.server_timestamp)
        sender_name = (
            "Vous" if own else (room.user_name(event.sender) or event.sender)
        )
        filename = event.body or "image"

        # Formater le message image
        image_url = getattr(event, "url", "") or getattr(event, "file", {}).get("url", "")
        if not image_url:
            # Essayer de récupérer l'URL depuis le contenu
            content = getattr(event, "source", {}).get("content", {})
            image_url = content.get("url", "")
            if not image_url and "file" in content:
                image_url = content["file"].get("url", "")

        line = f"[dim]{timestamp}[/dim] [bold]{escape(sender_name)}[/bold] [image: {escape(filename)}]"

        # Stocker en mémoire
        self.message_log.setdefault(room.room_id, []).append(line)

        if room.room_id != self.active_room_id:
            self.unread[room.room_id] = self.unread.get(room.room_id, 0) + 1
            self._refresh_room_list()
            if not own:
                notify(
                    room.display_name or room.name or room_id,
                    sender_name,
                    f"[image: {filename}]",
                )
            return

        # Afficher dans la timeline
        timeline = self.query_one("#timeline", RichLog)
        timeline.write(line)

        # Tenter d'afficher l'image inline si URL disponible
        if image_url:
            result = format_image_message(
                sender_name,
                image_url,
                filename,
                self.client.creds.access_token,
                self.client.creds.homeserver,
            )
            if is_image_message(result):
                # Extraire le chemin et afficher
                parts = result.split(":", 2)
                if len(parts) == 3:
                    local_path = parts[1]
                    img_result = render_image(local_path)
                    if isinstance(img_result, bytes):
                        # Écrire directement sur le terminal
                        import sys

                        sys.stdout.write(img_result.decode("latin-1"))
                        sys.stdout.flush()
                    else:
                        timeline.write(f"  {img_result}")
            elif result:
                timeline.write(f"  {result}")

    async def _show_invite_dialog(
        self, room_id: str, room: MatrixRoom, inviter: str
    ) -> None:
        # On ne rejoint JAMAIS un salon automatiquement : une invitation est
        # signalée et exige une décision humaine explicite.
        await self.app.push_screen(InviteDialog(self.client, room_id, room, inviter))

    async def _on_send_error(self, room_id: str, message: str) -> None:
        room = self.client.rooms().get(room_id)
        name = room.display_name if room else room_id
        self.app.notify(
            f"Envoi bloqué — {escape(name)} : {escape(message)}",
            title="Unverified devices",
        )

    def action_focus_rooms(self) -> None:
        self.query_one("#room-list", ListView).focus()

    def action_focus_input(self) -> None:
        self.query_one("#composer", Input).focus()

    def action_clear_screen(self) -> None:
        """Clears the active room timeline (view + in-memory buffer)."""
        if self.active_room_id is None:
            self.app.notify("Pick a room first")
            return
        self.message_log.pop(self.active_room_id, None)
        self.unread[self.active_room_id] = 0
        self.query_one("#timeline", RichLog).clear()
        self._refresh_room_list()
        self.app.notify("Timeline cleared")

    def action_mark_read(self) -> None:
        if self.active_room_id is None:
            self.app.notify("Pick a room first")
            return
        self.unread[self.active_room_id] = 0
        self._refresh_room_list()

    def action_open_last_link(self) -> None:
        if self.active_room_id is None:
            self.app.notify("Pick a room first")
            return
        url = self.last_link.get(self.active_room_id)
        if not url:
            self.app.notify("No recent link in this room")
            return
        webbrowser.open(url)
        self.app.notify(f"Opening: {url}")

    def action_sync_status(self) -> None:
        label, _ = SYNC_LABELS.get(self.client.sync_state, ("idle", "#565f89"))
        if self.client.sync_state == "online":
            label = "online"
        self.app.notify(
            f"Sync status: [bold]{label}[/bold]",
            title="Matrix",
        )

    def action_insert_slash(self, text: str) -> None:
        composer = self.query_one("#composer", Input)
        composer.value = text
        composer.cursor_position = len(text)
        composer.focus()

    async def logout_and_return_to_login(self) -> None:
        await self.client.logout()
        self.app.notify("Signed out, back to the login screen")
        await self.app.switch_screen(LoginScreen())