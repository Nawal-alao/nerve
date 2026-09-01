"""Thèmes de nerve.

Deux thèmes permutables à la volée, style OpenCode Zen :
- "opencode"     : fond quasi noir, accent orange pâle (#e59e72), ultra-flat
- "matrix_green" : fond vert-noir, accent vert néon (#50fa7b)

Les valeurs restent exposées sous les noms de variables de nerve
($bg, $pane, $surface, $primary, ...) pour que app.tcss n'en dépende pas.
register_themes() enregistre aussi les variables standards de Textual
($background, $foreground, $surface, $panel, $primary, ...) dont dépendent
les widgets internes (Input, Button, ...). Le thème actif est persisté dans
~/.config/nerve/config.json et rechargé au démarrage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from textual.app import App
from textual.theme import Theme

from .config import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_NAME = "opencode"

# Ordre de cycle de /theme.
THEME_ORDER = ("opencode", "matrix_green")


@dataclass(frozen=True)
class ThemeSpec:
    name: str
    label: str
    bg: str
    pane: str
    surface: str
    border: str
    hover: str
    text: str
    muted: str
    primary: str
    secondary: str
    accent: str
    section: str
    accent_text: str
    warning: str
    error: str
    success: str
    modal_border: str


THEMES: dict[str, ThemeSpec] = {
    "opencode": ThemeSpec(
        name="opencode",
        label="OpenCode Zen",
        bg="#0d0d0d",
        pane="#121212",
        surface="#181818",
        border="#262626",
        hover="#1c1c1c",
        text="#cccccc",
        muted="#555555",
        primary="#e59e72",
        secondary="#7a88cf",
        accent="#e59e72",
        section="#7a88cf",
        accent_text="#121212",
        warning="#d7a85f",
        error="#ff6f6f",
        success="#88c285",
        modal_border="none",
    ),
    "matrix_green": ThemeSpec(
        name="matrix_green",
        label="Matrix Green",
        bg="#050805",
        pane="#0f120f",
        surface="#0f120f",
        border="#2a402a",
        hover="#122414",
        text="#e0e0e0",
        muted="#666666",
        primary="#50fa7b",
        secondary="#3b5e3b",
        accent="#50fa7b",
        section="#3b5e3b",
        accent_text="#050805",
        warning="#ffd866",
        error="#ff6f6f",
        success="#50fa7b",
        modal_border="solid #2a402a",
    ),
}

_current_name = DEFAULT_NAME


def spec(name: str | None = None) -> ThemeSpec:
    return THEMES[name or _current_name]


def current() -> str:
    return _current_name


def tick(name: str) -> None:
    global _current_name
    if name in THEMES:
        _current_name = name


def label(name: str) -> str:
    return THEMES.get(name, THEMES[DEFAULT_NAME]).label


def cycle(name: str) -> str:
    """Prochain thème dans l'ordre, sans passer par le même."""
    if name not in THEME_ORDER:
        return THEME_ORDER[0]
    return THEME_ORDER[(THEME_ORDER.index(name) + 1) % len(THEME_ORDER)]


def accent() -> str:
    return spec().accent


def text() -> str:
    return spec().text


def success() -> str:
    return spec().success


def warning() -> str:
    return spec().warning


def error() -> str:
    return spec().error


def danger() -> str:
    return spec().error


def accent_text() -> str:
    return spec().accent_text


def muted() -> str:
    return spec().muted


def section() -> str:
    return spec().section


def register_themes(app: App) -> None:
    """Enregistre tous les thèmes et expose nos variables CSS."""
    for s in THEMES.values():
        variables = {
            "bg": s.bg,
            "pane": s.pane,
            "surface": s.surface,
            "border": s.border,
            "hover": s.hover,
            "text": s.text,
            "muted": s.muted,
            "primary": s.primary,
            "secondary": s.secondary,
            "accent": s.accent,
            "section": s.section,
            "accent_text": s.accent_text,
            "warning": s.warning,
            "error": s.error,
            "success": s.success,
            "modal_border": s.modal_border,
        }
        app.register_theme(
            Theme(
                name=s.name,
                dark=True,
                background=s.bg,
                foreground=s.text,
                primary=s.primary,
                secondary=s.secondary,
                accent=s.accent,
                surface=s.surface,
                panel=s.pane,
                warning=s.warning,
                error=s.error,
                success=s.success,
                variables=variables,
            )
        )


def activate(app: App, name: str | None = None) -> str:
    """Active le thème demandé (ou persisté) sur `app`, à faire AVANT
    le premier montage pour que les variables CSS existent à la compile.

    Note Textual 8 : les handlers de messages (dont on_mount) sont
    dispatchés sur toute la MRO. Chaque App doit donc n'appeler
    activate() qu'une seule fois dans son __init__."""
    register_themes(app)
    chosen = load_pref() if name is None else name
    app.theme = chosen if chosen in THEMES else DEFAULT_NAME
    tick(str(app.theme))
    return str(app.theme)


def load_pref() -> str:
    """Thème persisté, ou le défaut s'il est inconnu/absent."""
    try:
        data = json.loads(CONFIG_FILE.read_text())
        name = data.get("theme")
        if name in THEMES:
            return name
    except (OSError, ValueError):
        pass
    return DEFAULT_NAME


def save_pref(name: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps({"theme": name}, indent=2))
        CONFIG_FILE.touch()
    except OSError:
        # La persistance échoue (FS en lecture seule) : on reste fonctionnel.
        pass