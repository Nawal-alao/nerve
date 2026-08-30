"""Splash screen — bannière : "MATUI" en fonte _slant, dégradé de thème
sobre (muted → primary), auto-transition vers login/chat."""

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


def _to_rgb(hex_color: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    """'#rrggbb' -> (r, g, b). Retourne `fallback` si la valeur est invalide."""
    try:
        return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    except (ValueError, TypeError):
        return fallback


def _splash_art() -> Text:
    """Bannière 'MATUI' en fonte slant, dégradé de thème (muted → primary)."""
    spec = themes.spec()
    start = _to_rgb(spec.muted, (85, 85, 85))
    end = _to_rgb(spec.primary, (229, 158, 114))
    art = Figlet(font="slant").renderText("MATUI").rstrip("\n")
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