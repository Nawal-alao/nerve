"""Formatage de texte pour l'interface nerve : timeline, markdown inline,
heure et correspondance floue — fonctions pures, sans état Textual.

Regroupe les helpers extraits de `app.py` :
  _sender_color, _inline_markdown, _format_time, _fuzzy_score
plus leurs constantes privées (palette de couleurs, regex markdown, regex
d'URL). Dépend uniquement de `themes`.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from rich.markup import escape

from . import themes

# ---------------------------------------------------------------------------
# Aides de rendu (timeline)
# ---------------------------------------------------------------------------

# Palette des couleurs de sender : une couleur stable par identifiant,
# dérivée par hachage, pour que chaque personne garde toujours la sienne.
# (Pastels lisibles sur fond sombre, dans la famille du thème opencode.)
SENDER_COLORS = [
    "#a2d399", "#ffb4ab", "#ffd8a8", "#9ec3ff", "#c1ffb1",
    "#f0b8e0", "#baccb3", "#ffe58f", "#8cd8c8", "#d0d8ff",
]

_CODE_SPAN = re.compile(r"`([^`\n]+?)`")
_BOLD_SPAN = re.compile(r"\*\*([^*\n]+?)\*\*")
_ITALIC_SPAN = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_STRIKE_SPAN = re.compile(r"~~([^~\n]+?)~~")
_URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+")


def _sender_color(sender: str) -> str:
    digest = hashlib.md5(sender.encode("utf-8")).hexdigest()
    return SENDER_COLORS[int(digest[:8], 16) % len(SENDER_COLORS)]


def _inline_markdown(body: str) -> str:
    """Convertit le markdown inline le plus courant en markup Rich.

    Le corps est d'abord échappé (les crochets restent littéraux) puis on
    réinjecte du markup pour le code, le gras, l'italique et le barré.
    """
    text = escape(body)
    code = themes.accent()
    # Ordre : le code d'abord (le plus spécifique, délimité par des backticks
    # peu ambigus), puis le barré, le gras et enfin l'italique — pour éviter
    # qu'un motif ne se chevauche, chaque passe cible uniquement le texte
    # restant (délimiteurs `**`, `~~`, `*` non consécutifs).
    text = _CODE_SPAN.sub(lambda m: f"[{code}]{m.group(1)}[/{code}]", text)
    text = _STRIKE_SPAN.sub(r"[strike]\1[/strike]", text)
    text = _BOLD_SPAN.sub(r"[bold]\1[/bold]", text)
    text = _ITALIC_SPAN.sub(r"[italic]\1[/italic]", text)
    return text


def _format_time(timestamp_ms: int | None) -> str:
    if not timestamp_ms:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%H:%M")


def _fuzzy_score(query: str, candidate: str) -> float:
    """Score de correspondance floue (sous-séquence ordonnée).

    Renvoie un score >= 0 si `query` apparaît en sous-séquence dans
    `candidate` (insensible à la casse), -1 sinon. Bonus pour les lettres
    consécutives et un préfixe exact, type fzf.
    """
    q = query.casefold()
    c = candidate.casefold()
    if not q:
        return 0.0
    score = 0.0
    prev = -1
    for ch in q:
        pos = c.find(ch, prev + 1)
        if pos == -1:
            return -1.0
        score += 1.5 if pos == prev + 1 else 0.4
        prev = pos
    if c.startswith(q):
        score += 5.0
    return score