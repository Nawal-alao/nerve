"""Notifications desktop pour shelltrix.

Utilise `notify-send` (Linux/BSD via libnotify) pour afficher une notification
quand un message arrive dans un salon inactif. Désactivable via la config
(`notifications_enabled`, défaut : activé).
"""

from __future__ import annotations

import shutil
import subprocess

from .config import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.json"


def is_enabled() -> bool:
    """Vrai si les notifications desktop sont activées (défaut : True)."""
    try:
        import json

        data = json.loads(CONFIG_FILE.read_text())
        return bool(data.get("notifications_enabled", True))
    except (OSError, ValueError):
        return True


def notify(room_name: str, sender: str, body: str) -> None:
    """Envoie une notification desktop via notify-send.

    Silencieux si :
    - les notifications sont désactivées dans la config
    - notify-send n'est pas installé
    """
    if not is_enabled():
        return
    if not shutil.which("notify-send"):
        return

    body_clean = body.replace("\n", " ")[:200]
    try:
        subprocess.Popen(
            [
                "notify-send",
                "--app-name=shelltrix",
                "--category=im.received",
                f"[{room_name}] {sender}",
                body_clean,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
