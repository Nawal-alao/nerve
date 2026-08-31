"""Splash screen — bannière "NERVE" en fonte smslant, dégradé de thème sobre
(muted → text, lettre initiale en primary), fondu du logo, typage discret de
la tagline puis curseur terminal subtil, auto-transition vers login/chat.
Aucune couleur en dur : tout vient des tokens du thème actif."""

from __future__ import annotations

import asyncio

from pyfiglet import Figlet
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Static

from .. import __version__, themes


# --- Constantes d'animation (aucune couleur ici : viole la règle absolue) ---
_TAGLINE = "secure · private · minimal"   # texte tapé dans la tagline
_CURSOR = "▎"                             # curseur terminal fin et subtil
_FADE_MS = 0.5                            # durée du fondu d'apparition du logo
_FADE_STEPS = 12                          # trames du fondu (styles.opacity)
_TAG_WAIT = 0.3                           # pause entre fondu et frappe
_TAG_TICK = 0.05                          # cadence d'apparition des lettres
_CURSOR_BLINK = 0.55                      # cadence douce du clignotement
_AUTO_MS = 3.0                            # auto-transition (laisse le temps
                                          # de voir la séquence complète)


def _lerp(percent: float, start: tuple[int, int, int], end: tuple[int, int, int]) -> tuple[int, int, int]:
    """Interpole deux couleurs RGB en 0..255 selon `percent` dans [0, 1]."""
    return tuple(
        round(a + (b - a) * percent) for a, b in zip(start, end)
    )


def _to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    """'#rrggbb' -> (r, g, b), ou None si la valeur est invalide.

    Les tokens du thème ($muted, $text, $primary...) produisent toujours
    des hex valides ; None est un garde-fou pur (aucune couleur en dur ici)."""
    try:
        return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    except (ValueError, TypeError):
        return None


def _splash_art() -> Text:
    """Bannière 'NERVE' en fonte smslant : dégradé sobre $muted → $text,
    avec la lettre initiale accentuée en $primary (signal discret)."""
    spec = themes.spec()
    start = _to_rgb(spec.muted)
    end = _to_rgb(spec.text)
    art = Figlet(font="smslant").renderText("NERVE").rstrip("\n")
    if start is None or end is None:
        # Garde-fou : le thème est invalide, on rend le texte sans couleur.
        return Text(art)
    lines = art.split("\n")
    total = sum(len(line) for line in lines)
    out = Text()
    pos = 0.0
    for idx, line in enumerate(lines):
        for ch in line:
            r, g, b = _lerp(pos / total if total else 0.0, start, end)
            out.append(ch, style=f"rgb({r},{g},{b})")
            pos += 1.0
        if idx < len(lines) - 1:
            out.append("\n")
    # Accent : la première lettre du logo passe en $primary.
    out.stylize(spec.primary, 0, 1)
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
        self._animation_started = False
        self._tagline: Static | None = None
        self._typed = 0
        self._cursor_on = True
        # Timers de l'animation : toujours stockés, toujours arrêtés
        # explicitement (.stop()) — jamais via la valeur de retour du callback
        # (`return False` est ignoré par Textual 8.2.8).
        self._fade_timer: Timer | None = None
        self._wait_timer: Timer | None = None
        self._typing_timer: Timer | None = None
        self._blink_timer: Timer | None = None
        self._auto_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-wrap"):
            with Vertical(id="splash-group"):
                yield Static(_splash_art(), id="splash-art")
                yield Static("", id="splash-sub")  # remplie par la frappe
                yield Static("enter   continue\nesc     skip", id="splash-hint")
            yield Static("nerve // encrypted", id="splash-detail")
            yield Static(f"v{__version__}", id="splash-version")

    def on_mount(self) -> None:
        if self._animation_started:
            return
        self._animation_started = True
        self._adapt_layout()
        self._animate_logo()
        self._auto_timer = self.set_timer(_AUTO_MS, self._launch)

    def on_unmount(self) -> None:
        # Filet de sécurité : si le screen est un jour popé, plus aucun timer
        # ne survivra (idempotent — stop() sur un timer déjà arrêté est sans
        # effet).
        self._stop_animation()

    def _adapt_layout(self) -> None:
        """Adaptation discrète aux petits terminaux : le CSS Textual n'a pas
        de media queries, on bascule donc des classes compacts en Python.

        Le bloc complet (logo + tagline + hint + marges) tient en 16 lignes ;
        en dessous on serre d'abord le hint ('splash-squeeze', 14-15 lignes),
        puis on le masque et resserre la tagline ('splash-tiny', < 14)."""
        h = self.size.height
        if h >= 16:
            return
        self.add_class("-splash-squeeze")
        if h < 14:
            self.add_class("-splash-tiny")

    def _animate_logo(self) -> None:
        """Fondu d'apparition du logo, puis enchaîne la frappe de la tagline.

        Le fondu est piloté manuellement via `styles.opacity` (la propriété
        `opacity` du widget n'est pas animable par `.animate()` dans cette
        version de Textual, pas de setter) — trame à trame, sans dépendance.
        Le timer est stocké et stoppé explicitement à la dernière trame."""
        self._art = self.query_one("#splash-art", Static)
        self._art.styles.opacity = 0.0
        self._fade_step = 0
        self._fade_timer = self.set_interval(_FADE_MS / _FADE_STEPS, self._fade_tick)

    def _fade_tick(self) -> None:
        if not self.is_mounted:
            return
        self._fade_step += 1
        self._art.styles.opacity = min(1.0, self._fade_step / _FADE_STEPS)
        if self._fade_step < _FADE_STEPS:
            return
        self._art.styles.opacity = 1.0
        self._stop_timer(self._fade_timer)
        # Chaîne en AVAL, une seule fois : pause puis frappe de la tagline.
        self._wait_timer = self.set_timer(_TAG_WAIT, self._begin_typing)

    def _stop_timer(self, timer: Timer | None) -> None:
        """Arrête un timer s'il existe (guard contre None)."""
        if timer is not None:
            timer.stop()

    def _begin_typing(self) -> None:
        if not self.is_mounted:
            return
        self._tagline = self.query_one("#splash-sub", Static)
        self._tagline.update("")
        self._typed = 0
        self._typing_timer = self.set_interval(_TAG_TICK, self._type_tick)

    @staticmethod
    def _tagline_text(body: str, cursor_on: bool) -> Text:
        """Tagline en $muted avec curseur terminal en fin (toujours présent,
        rendu en couleur de fond quand il est "éteint" → largeur stable)."""
        spec = themes.spec()
        muted = Style(color=spec.muted)
        text = Text(body, style=muted)
        text.append(_CURSOR, style=muted if cursor_on else Style(color=spec.bg))
        return text

    def _type_tick(self) -> None:
        if not self.is_mounted:
            return
        assert self._tagline is not None
        self._typed += 1
        self._cursor_on = True
        self._tagline.update(self._tagline_text(_TAGLINE[: self._typed], True))
        if self._typed < len(_TAGLINE):
            return
        # Texte entièrement tapé : on arrête la frappe, puis on passe au
        # clignotement du curseur — aucun relance de la chaîne.
        self._stop_timer(self._typing_timer)
        self._blink_timer = self.set_interval(_CURSOR_BLINK, self._cursor_tick)

    def _cursor_tick(self) -> None:
        if not self.is_mounted:
            return
        self._cursor_on = not self._cursor_on
        # Le curseur reste présent (largeur constante → aucun décalage du
        # groupe) ; on le rend juste invisible via la couleur du fond.
        self._tagline.update(self._tagline_text(_TAGLINE, self._cursor_on))

    def _stop_animation(self) -> None:
        """Arrête tous les timers d'animation encore actifs (guards None)."""
        if self._fade_timer is not None:
            self._fade_timer.stop()
        if self._wait_timer is not None:
            self._wait_timer.stop()
        if self._typing_timer is not None:
            self._typing_timer.stop()
        if self._blink_timer is not None:
            self._blink_timer.stop()
        if self._auto_timer is not None:
            self._auto_timer.stop()

    def _launch(self) -> None:
        if self._launched:
            return
        self._launched = True
        self._stop_animation()
        asyncio.create_task(self.app.begin())

    def action_skip(self) -> None:
        self._launch()