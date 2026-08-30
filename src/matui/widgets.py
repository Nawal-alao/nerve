"""Widgets UI maison réutilisables, extraits de `app.py`.

`_SendButton` : bouton d'envoi « → » plat (un Static cliquable). Aucun
import vers `app`, `screens` ou `dialogs` — il opère sur son écran hôte
par introspection.
"""

from __future__ import annotations

from textual import events
from textual.widgets import Input, Static


class _SendButton(Static):
    """Bouton d'envoi « → » plat : un Static cliquable.

    Un vrai Button Textual impose `line-pad >= 1` et une hauteur minimale de
    3 lignes, ce qui rend son libellé illisible dans la barre de saisie
    (hauteur 1). On remplace donc par un Static dont le clic relance le même
    chemin d'envoi que la touche Entrée.
    """

    def on_click(self, event: events.Click) -> None:
        event.stop()
        screen = self.screen
        if screen.active_room_id is None:
            return
        self.run_worker(screen._dispatch_compose(screen.query_one("#composer", Input)))