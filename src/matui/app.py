"""Interface Textual de matui.

Deux écrans :
- LoginScreen : demandé seulement au tout premier lancement (pas de
  credentials.json trouvé). Fait un login classique par mot de passe et
  sauvegarde un access token réutilisable.
- ChatScreen : l'interface principale, à trois zones — liste des salons,
  timeline du salon actif, champ de saisie.
"""

from __future__ import annotations

import asyncio
import time
import webbrowser

from nio import MatrixRoom, RoomMessageText
from pyfiglet import Figlet
from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Rule,
    Static,
)


from . import themes
from .config import (
    Credentials,
    StoreLockedError,
    decrypt_store,
    recovery_has_verifier,
    regenerate_recovery_secret,
    remove_store,
    reveal_recovery_secret,
)
from .formatting import (
    _URL_RE,
    _format_time,
    _fuzzy_score,
    _inline_markdown,
    _sender_color,
)
from .matrix_client import MatuiClient
from .sidebar import _sidebar_room_markup, _sidebar_session_markup
from .widgets import _SendButton
from .dialogs.command_palette import CommandPalette

# ---------------------------------------------------------------------------
# Aides de rendu (timeline)
# ---------------------------------------------------------------------------

# Correspondance état de sync → (libellé, couleur) pour le header.
SYNC_LABELS = {
    "connecting": ("offline", "#ff6f6f"),
    "syncing": ("syncing…", "#d7a85f"),
    "online": ("online", "#88c285"),
    "offline": ("off-line", "#ff6f6f"),
}

# Les couleurs markup (ACCENT/DANGER) suivent le thème actif : elles sont
# re-évaluées à chaque bascule de thème par _apply_theme_globals().
# Après le découpage en modules, les consommateurs lisent themes.accent()
# et themes.danger() directement (cf. NOTES.md). Les globals restent ici
# maintenues par MatuiApp mais n'ont plus d'utilisation.
ACCENT = "a2d399"
DANGER = "ffb4ab"


def _apply_theme_globals() -> None:
    """Repointe les constantes markup (ACCENT/DANGER) sur le thème actif."""
    global ACCENT, DANGER
    ACCENT = themes.accent()
    DANGER = themes.danger()


_apply_theme_globals()


# ---------------------------------------------------------------------------
# Écran de connexion
# ---------------------------------------------------------------------------


class LoginScreen(Screen):
    """Écran de connexion initial (une seule fois, ensuite le token est
    réutilisé automatiquement)."""

    def compose(self) -> ComposeResult:
        with Vertical(id="login-wrap"):
            with Vertical(id="login-card"):
                yield Static("◆ matui", id="brand")
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
            creds = await MatuiClient.login(homeserver, user_id, password)
        except Exception as exc:  # noqa: BLE001 — on affiche l'erreur à l'écran
            self._set_status(f"Connection failed: {exc}", kind="error")
            self._set_loading(False)
            return

        self._set_status("Connected, opening the chat…", kind="success")
        creds.save()
        app: MatuiApp = self.app  # type: ignore[assignment]
        await app.start_chat(creds)


# ---------------------------------------------------------------------------
# Écran de chat
# ---------------------------------------------------------------------------


class ChatScreen(Screen):
    """L'interface principale : salons à gauche, timeline + saisie à droite."""

    BINDINGS = [
        ("ctrl+r", "focus_rooms", "Rooms"),
        ("ctrl+l", "focus_input", "Compose"),
        ("ctrl+k", "clear_screen", "Clear"),
        ("ctrl+d", "toggle_sidebar", "Sidebar"),
    ]

    def __init__(self, client: MatuiClient) -> None:
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
        # Jeton de sync observé (sidebar SESSION) : heure (wall) du dernier
        # changement de next_batch, pour afficher "Refresh Xs ago".
        self._last_nb: str | None = None
        self._nb_time: float | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Static("No room selected", id="room-title")
            yield Static("● offline", id="sync-status")
            yield Static("", id="clock")
        with Horizontal(id="main"):
            with Vertical(id="room-panel"):
                yield Static("◆ matui", id="brand-sidebar")
                yield Static("ROOMS", id="room-list-header")
                yield ListView(id="room-list")
            with Vertical(id="chat-area"):
                yield RichLog(id="timeline", wrap=True, highlight=True, markup=True)
                yield ListView(id="suggestion-list")
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
        self.client.on_invite = self._show_invite_dialog
        self.client.on_sas_request = self._show_sas_dialog
        self.client.on_send_error = self._on_send_error
        self.set_interval(1.0, self._tick_status)
        self._tick_status()  # "syncing…" during the first sync
        await self.client.start()
        self._refresh_room_list()
        timeline = self.query_one("#timeline", RichLog)
        timeline.write(
            "\n[dim]· · ·  Pick a room from the list to start chatting  · · ·[/dim]"
        )

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
        label, color = SYNC_LABELS.get(
            self.client.sync_state, ("idle", themes.muted())
        )
        if self.client.sync_state == "online":
            color = themes.accent()
        self.query_one("#sync-status", Static).update(f"[{color}]●[/{color}] {label}")
        self.query_one("#clock", Static).update(time.strftime("%H:%M"))
        self._refresh_sidebar()

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
        ordered = sorted(
            self.client.rooms().items(),
            key=lambda kv: (
                self.unread.get(kv[0], 0) == 0,  # les salons non-lus d'abord
                (kv[1].display_name or kv[0]).lower(),
            ),
        )
        for room_id, room in ordered:
            name = Label(escape(room.display_name or room_id), classes="room-name")
            unread = self.unread.get(room_id, 0)
            row = (
                Horizontal(
                    name,
                    Label(str(unread), classes="room-badge"),
                    classes="room-row",
                )
                if unread
                else Horizontal(name, classes="room-row")
            )
            item = ListItem(row)
            item.data_room_id = room_id  # type: ignore[attr-defined]
            if room_id == self.active_room_id:
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
        lines = [f"[bold][{ACCENT}]/{cmd}[/{ACCENT}]  {desc}" for cmd, desc in self.SLASH_HELP.items()]
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
            self._update_suggestions(event.value)

    def _matching_commands(self, query: str) -> list[str]:
        scored = [
            (score, cmd)
            for cmd in self.SLASH_COMMANDS
            if (score := _fuzzy_score(query, cmd[1:])) >= 0
        ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [cmd for _, cmd in scored]

    def _update_suggestions(self, value: str) -> None:
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
                    f"[bold][{ACCENT}]{escape(cmd)}[/{ACCENT}][/bold]"
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
        self.query_one("#suggestion-list", ListView).styles.display = "none"

    def _accept_suggestion(self) -> None:
        commands = self._suggestion_commands
        if not (0 <= self._suggestion_index < len(commands)):
            self._hide_suggestions()
            return
        cmd = commands[self._suggestion_index]
        self._hide_suggestions()
        composer = self.query_one("#composer", Input)
        composer.value = f"{cmd} "
        composer.cursor_position = len(composer.value)
        composer.focus()

    def on_key(self, event: events.Key) -> None:
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
            line = (
                f"[dim]{timestamp}[/dim] "
                f"[bold][{ACCENT}]› Vous[/{ACCENT}][/bold]  {body}"
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
            return
        self.query_one("#timeline", RichLog).write(line)

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


# ---------------------------------------------------------------------------
# Rejoindre un salon par alias — saisie d'un #alias:serveur
# ---------------------------------------------------------------------------


class JoinRoomDialog(ModalScreen[None]):
    """Small modal asking for the alias of the room to join."""

    BINDINGS = [
        ("escape", "dismiss", "Cancel"),
    ]

    def __init__(self, chat: ChatScreen) -> None:
        super().__init__()
        self.chat = chat

    def compose(self) -> ComposeResult:
        with Vertical(id="jr-dialog"):
            yield Static("Join a room", id="jr-title")
            yield Input(placeholder="#room:server", id="jr-alias")
            with Horizontal(id="jr-buttons"):
                yield Button("Join", id="jr-confirm", variant="primary")
                yield Button("Cancel", id="jr-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#jr-alias", Input).focus()

    @staticmethod
    def _host_hint(chat: ChatScreen) -> str:
        server = ""
        for room in chat.client.rooms().values():
            canonical = getattr(room, "canonical_alias", None)
            if canonical and ":" in canonical:
                return canonical.rsplit(":", 1)[1]
            room_id_parts = room.room_id.split(":")
            if len(room_id_parts) > 1:
                server = room_id_parts[1]
                break
        return server

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "jr-confirm":
            asyncio.create_task(self._join())
        elif event.button.id == "jr-cancel":
            self.dismiss()
            self.app.call_after_refresh(self.chat.action_focus_input)

    async def _join(self) -> None:
        raw = self.query_one("#jr-alias", Input).value.strip()
        if not raw:
            self.app.notify("Type a room alias", severity="error")
            return
        alias = raw
        if not alias.startswith("#"):
            if ":" not in alias:
                host = self._host_hint(self.chat)
                alias = f"#{alias}:{host}" if host else f"#{alias}"
            else:
                alias = f"#{alias}"
        self.dismiss()
        await self.chat.client.join_room(alias)
        await self.chat._refresh_room_list_async()
        self.app.call_after_refresh(self.chat.action_focus_input)


# ---------------------------------------------------------------------------
# Clé de récupération de session (E2EE) — gestion et restauration
# ---------------------------------------------------------------------------


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
                yield Button("Reveal", id="rec-reveal", variant="primary")
                yield Button("Regenerate", id="rec-regenerate")
                yield Button("Close", id="rec-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rec-close":
            self.dismiss()
        elif event.button.id == "rec-reveal":
            self._reveal()
        elif event.button.id == "rec-regenerate":
            self._regenerate()

    def _set_key(self, secret: str, note: str) -> None:
        self.query_one("#rec-key", Static).update(
            f"[bold][{ACCENT}]{secret}[/{ACCENT}][/bold]\n[dim]{note}[/dim]"
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
            button.label = "Confirm regenerate"
            button.variant = "error"
            self.app.notify(
                "Regenerating invalidates the previous recovery key",
                title="Recovery key",
            )
            return
        try:
            secret = regenerate_recovery_secret()
        except Exception as exc:  # noqa: BLE001 — surface l'erreur à l'écran
            self.app.notify(f"Could not regenerate the key: {exc}", severity="error")
            return
        self._confirming = False
        button.label = "Regenerate"
        button.variant = "default"
        self._set_key(secret, "The previous recovery key is now invalid.")
        self.app.notify("Recovery key regenerated", title="Recovery key")


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
                yield Button("Restore", id="unlock-restore", variant="primary")
                yield Button("Sign out & start fresh", id="unlock-logout")

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


# ---------------------------------------------------------------------------
# Vérification d'appareil par emoji (SAS) — confirmation humaine requise
# ---------------------------------------------------------------------------


class SasDialog(ModalScreen[None]):
    """Shows the verification emojis and demands a human decision."""

    def __init__(
        self,
        client: MatuiClient,
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
        with Vertical(id="sas-dialog"):
            yield Static("Device verification", id="sas-title")
            yield Static(
                f"[dim]{escape(self.user_id)}[/dim] [dim]· device[/dim] "
                f"[{ACCENT}]{escape(self.device_id)}[/{ACCENT}]",
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
                yield Button("Verify", id="sas-confirm", variant="success")
                yield Button("Reject", id="sas-reject", variant="error")
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


# ---------------------------------------------------------------------------
# Confirmation humaine des invitations
# ---------------------------------------------------------------------------


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
        with Vertical(id="invite-dialog"):
            yield Static("Room invitation", id="invite-title")
            yield Static(
                f"[bold]{escape(name)}[/bold]\n"
                f"[dim]{escape(self.room_id)}[/dim]",
                id="invite-room",
            )
            yield Static(
                f"from [bold][{ACCENT}]{escape(self.inviter)}[/{ACCENT}][/bold]",
                id="invite-sender",
            )
            yield Static(
                "Join this room? A malicious inviter could spam or trick you.",
                id="invite-hint",
            )
            with Horizontal(id="invite-actions"):
                yield Button("Accept", id="invite-accept", variant="success")
                yield Button("Decline", id="invite-decline", variant="error")

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


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Splash screen (bannière hacking scene : "MATUI" en fonte _slant, dégradé
# façon lolcat, auto-transition vers login/chat).
# ---------------------------------------------------------------------------


def _hsv(hue: float, sat: float, val: float) -> tuple[int, int, int]:
    """HSV -> (r, g, b) en 0..255, hue dans [0, 1)."""
    i = int(hue * 6)
    f = hue * 6 - i
    p = val * (1 - sat)
    q = val * (1 - f * sat)
    t = val * (1 - (1 - f) * sat)
    r, g, b = (
        (val, t, p),
        (q, val, p),
        (p, val, t),
        (p, q, val),
        (t, p, val),
        (val, p, q),
    )[i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


def _splash_art() -> Text:
    """Bannière 'MATUI' en fonte slant, teintée arc-en-ciel dégradé."""
    art = Figlet(font="slant").renderText("MATUI").rstrip("\n")
    lines = art.split("\n")
    total = sum(len(line) for line in lines)
    out = Text()
    hue = 0.0
    for idx, line in enumerate(lines):
        for ch in line:
            r, g, b = _hsv(hue, 0.85, 0.95)
            out.append(ch, style=f"rgb({r},{g},{b})")
            hue += 1.0 / total if total else 0.0
        if idx < len(lines) - 1:
            out.append("\n")
    return out


class SplashScreen(Screen):
    """Bannière de démarrage : ASCII art animé puis entrée dans l'app."""

    BINDINGS = [
        ("escape", "skip", "Skip"),
        ("enter", "skip", "Skip"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._launched = False

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-wrap"):
            yield Static(_splash_art(), id="splash-art")
            yield Static("// encrypted matrix client — the grid awaits", id="splash-sub")
            yield Static("[dim]enter / esc to skip[/dim]", id="splash-hint")

    def on_mount(self) -> None:
        self.set_timer(2.4, self._launch)

    def _launch(self) -> None:
        if self._launched:
            return
        self._launched = True
        asyncio.create_task(self.app.begin())

    def action_skip(self) -> None:
        self._launch()


class MatuiApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "matui"
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
        await self.push_screen(SplashScreen())

    async def begin(self) -> None:
        """Après le splash : login ou reprise du chat selon les creds."""
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
        client = MatuiClient(creds=creds)
        try:
            client.load_local_store()
        except StoreLockedError:
            await self.push_screen(StoreUnlockDialog(creds, client))
            return
        await self.push_screen(ChatScreen(client))


def run() -> None:
    MatuiApp().run()


if __name__ == "__main__":
    run()