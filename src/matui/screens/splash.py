"""Splash screen — bannière hacking scene : "MATUI" en fonte _slant, dégradé
façon lolcat, auto-transition vers login/chat."""

from __future__ import annotations

import asyncio

from pyfiglet import Figlet
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static


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