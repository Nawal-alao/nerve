"""Splash screen — bannière : "NERVE" en fonte smslant, dégradé de thème
sobre (muted → text, lettre initiale en primary), auto-transition vers
login/chat. Aucune couleur en dur : tout vient des tokens du thème actif."""

from __future__ import annotations

import asyncio

from pyfiglet import Figlet
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from .. import themes


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

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-wrap"):
            with Vertical(id="splash-group"):
                yield Static(_splash_art(), id="splash-art")
                yield Static("secure · private · minimal", id="splash-sub")
                yield Static("enter   continue\nesc     skip", id="splash-hint")
            yield Static("nerve // encrypted", id="splash-detail")

    def on_mount(self) -> None:
        self.set_timer(2.4, self._launch)

    def _launch(self) -> None:
        if self._launched:
            return
        self._launched = True
        asyncio.create_task(self.app.begin())

    def action_skip(self) -> None:
        self._launch()