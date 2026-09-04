"""Formatage de texte pour l'interface neurite : timeline, markdown inline,
heure et correspondance floue — fonctions pures, sans état Textual.

Regroupe les helpers extraits de `app.py` :
  _sender_color, _inline_markdown, _format_time, _fuzzy_score
plus leurs constantes privées (palette de couleurs, regex markdown, regex
d'URL). Dépend uniquement de `themes`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from rich.markup import escape

from . import themes

# ---------------------------------------------------------------------------
# Timeline conversationnelle
# ---------------------------------------------------------------------------

# Un séparateur temporel (ligne + heure) sépare deux messages du même salon
# quand le silence entre eux dépasse ce seuil.
TIME_GAP_SEPARATOR_MS = 5 * 60 * 1000


@dataclass
class TimelineEntry:
    """Un message de la timeline, sous forme structurée.

    Le rendu (groupage par expéditeur, séparateurs temporels) est calculé à
    l'affichage, pas stocké : c'est ce qui permet une conversation groupée
    au lieu d'un journal répétitif.
    """

    sender: str  # user_id complet (@alice:hs)
    display_name: str  # nom d'affichage résolu (pour le header du bloc)
    is_own: bool
    time_ms: int  # timestamp serveur en millisecondes
    body: str  # corps déjà échappé + markdown inline
    event_id: str = ""  # identifiant serveur (dédup pagination/historique)
    msgtype: str = "m.text"  # type de message (m.text, m.emote, m.image, …)
    has_mention: bool = False  # vrai si ce message nous mentionne (@user)
    is_image: bool = False
    image_hint: str = ""  # ex. nom de fichier pour le placeholder
    timestamp: str = field(default="")  # "HH:MM" pré-calculé


@dataclass
class TimelineContext:
    """État de groupage en cours pour un salon.

    `last_sender`/`last_time_ms` reflètent la dernière entrée rendue : ils
    servent à décider si la prochaine entrée continue le bloc courant, ouvre
    un nouveau bloc, ou nécessite un séparateur temporel.
    """

    last_sender: str | None = None
    last_time_ms: int = 0


def interval_time_gap(prev_ms: int, curr_ms: int) -> bool:
    """Vrai si le silence entre deux messages dépasse le seuil (5 min)."""
    return (curr_ms - prev_ms) >= TIME_GAP_SEPARATOR_MS


def body_mentions_user(body: str, user_id: str) -> bool:
    """Vrai si le corps du message mentionne explicitement `user_id`.

    Reconnaît à la fois l'identifiant complet (`@local:serveur`) et le
    localpart simple (`@local`). Fonction pure, testée.
    """
    if not body or not user_id:
        return False
    full = user_id.strip()
    if "@" not in full:
        return False
    localpart = full.split(":", 1)[0]
    for token in (full, localpart):
        if token in body:
            return True
    return False


def format_timeline_entries(
    entries: list[TimelineEntry],
    ctx: TimelineContext,
    *,
    header_for: Callable[[TimelineEntry], str],
) -> tuple[list[str], TimelineContext]:
    """Convertit une liste d'entrées en lignes Rich groupées en blocs.

    Applique les règles (dans l'ordre) :
      - nouveau salon (ctx vide) → ouvre un bloc (header) + première ligne ;
      - silence > seuil → séparateur temporel, puis header + ligne ;
      - même expéditeur consécutif → simple ligne indentée (continuation) ;
      - expéditeur différent → header + ligne.

    `header_for` est un callable(entry) → markup Rich du header de bloc
    (ex. "› Vous" ou "‹ Alice"), fourni par l'appelant car il dépend du thème
    et des couleurs de sender.

    Retourne (lignes, contexte_final) : le contexte final s'applique à la
    suite de la liste, pour permettre un rendu incrémental cohérent avec le
    rendu complet.
    """
    out: list[str] = []
    indent = "        "
    for e in entries:
        if ctx.last_sender is None:
            # Début : on ouvre un bloc.
            out.append(f"{indent}{header_for(e)}")
            out.append(f"{indent}{e.body}")
        elif interval_time_gap(ctx.last_time_ms, e.time_ms):
            # Silence trop long : séparateur temporel puis nouveau bloc.
            ts = f"{e.timestamp} " if e.timestamp else ""
            out.append("")
            out.append(f"[dim]{ts}{'─' * 36}[/dim]")
            out.append(f"{indent}{header_for(e)}")
            out.append(f"{indent}{e.body}")
        elif e.sender == ctx.last_sender:
            # Même expéditeur, pas de silence : on continue le bloc.
            out.append(f"{indent}{e.body}")
        else:
            # Changement d'expéditeur : nouvel indicateur de bloc.
            out.append(f"{indent}{header_for(e)}")
            out.append(f"{indent}{e.body}")
        ctx.last_sender = e.sender
        ctx.last_time_ms = e.time_ms
    return out, ctx


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


def highlight_mentions(markup: str, user_id: str) -> str:
    """Enveloppe les mentions de `user_id` dans un markup accent fort.

    À appeler APRÈS `_inline_markdown` : le corps est déjà échappé, les
    mentions `@localpart` ou `@local:serveur` sont donc repérables telles
    quelles. On évite les faux positifs : une mention partielle (`@bob2`)
    ou un identifiant différent (`@bob:autre`) n'est pas touchée.
    """
    if not user_id or "@" not in user_id:
        return markup
    localpart = user_id.split(":", 1)[0]
    accent = themes.accent()
    full = re.escape(user_id)
    bare = re.escape(localpart)

    def _repl(m: re.Match) -> str:
        return f"[bold][{accent}]{m.group(0)}[/{accent}][/bold]"

    # `localpart` contient déjà le '@' (ex. "@alice") ; on le cherche tel quel,
    # en excluant les faux positifs `@bob2` / `@bob:autre`.
    pattern = rf"({full})|({bare}(?![:\w]))"
    return re.sub(pattern, _repl, markup)


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