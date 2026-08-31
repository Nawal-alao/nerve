"""Rendu inline des images dans le terminal.

Détecte les messages m.image et les affiche via :
- Protocole graphics Kitty (Kitty, WezTerm, ghostty)
- Sixel (XTerm, mlterm, WezTerm, foot, Alacritty, Konsole)

Fallback : affiche un placeholder [image: nom] si le terminal ne supporte
aucun protocole.
"""

from __future__ import annotations

import base64
import os
import struct
import sys
import tempfile
from pathlib import Path

from .config import CONFIG_DIR

# Terminaux supportant le protocole graphics Kitty
_KITTY_TERMINALS = ("kitty", "wezterm", "ghostty")

# Terminaux supportant Sixel
_SIXEL_TERMINALS = ("xterm", "mlterm", "foot", "alacritty", "konsole", "wezterm")

_images_dir = CONFIG_DIR / "images"


def _detect_terminal() -> str:
    """Détecte le type de terminal pour choisir le protocole."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()
    # Vérifier TERM_PROGRAM d'abord (plus fiable)
    if term_program in _KITTY_TERMINALS:
        return "kitty"
    if "kitty" in term:
        return "kitty"
    # Vérifier le support Kitty via KITTY_WINDOW_ID
    if os.environ.get("KITTY_WINDOW_ID"):
        return "kitty"
    # Vérifier WezTerm
    if os.environ.get("WEZTERM_EXECUTABLE") or term_program == "wezterm":
        return "kitty"  # WezTerm supporte le protocole Kitty
    # Vérifier ghostty
    if term_program == "ghostty" or "ghostty" in term:
        return "kitty"
    # Vérifier Sixel
    if "xterm" in term or term_program == "iterm.app":
        # iTerm2 supporte Sixel via certaines versions
        return "sixel"
    if "mlterm" in term:
        return "sixel"
    if "foot" in term:
        return "sixel"
    if "alacritty" in term:
        # Alacritty ne supporte PAS Sixel nativement (au moment de l'écriture)
        return "none"
    if "konsole" in term:
        return "sixel"
    return "none"


# Cache du protocole détecté
_protocol: str | None = None


def get_protocol() -> str:
    """Renvoie le protocole détecté : 'kitty', 'sixel' ou 'none'."""
    global _protocol
    if _protocol is None:
        _protocol = _detect_terminal()
    return _protocol


def reset_cache() -> None:
    """Réinitialise le cache (pour les tests)."""
    global _protocol
    _protocol = None


def download_image(mxc_url: str, access_token: str, homeserver: str) -> Path | None:
    """Télécharge une image depuis une URL Matrix (mxc://).

    Chemin du fichier téléchargé en cas de succès, None sinon.
    """
    import asyncio
    import urllib.parse
    import urllib.request

    # Convertir mxc:// en URL HTTP
    if not mxc_url.startswith("mxc://"):
        return None
    mxc_path = mxc_url[6:]  # Retirer mxc://
    base_url = homeserver.rstrip("/")
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    download_url = f"{base_url}/_matrix/media/r0/download/{mxc_path}"

    # Créer le dossier de cache
    _images_dir.mkdir(parents=True, exist_ok=True)

    # Nom de fichier basé sur le hash de l'URL
    url_hash = base64.urlsafe_b64encode(mxc_url.encode()).decode()[:24]
    ext = _guess_extension(mxc_path)
    local_path = _images_dir / f"{url_hash}{ext}"

    # Si déjà en cache, retourner
    if local_path.exists() and local_path.stat().st_size > 0:
        return local_path

    # Télécharger
    try:
        req = urllib.request.Request(download_url)
        req.add_header("Authorization", f"Bearer {access_token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        local_path.write_bytes(data)
        return local_path
    except Exception:
        return None


def _guess_extension(path: str) -> str:
    """Devine l'extension du fichier depuis le chemin MXC."""
    if "/" in path:
        name = path.split("/")[-1]
    else:
        name = path
    # Extraire l'extension si présente
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            return f".{ext}"
    return ".png"  # Défaut


def render_image_kitty(image_path: str | Path, max_width: int = 80) -> bytes:
    """Génère les séquences d'échappement Kitty pour afficher une image.

    Utilise le transfert en base64 chunké du protocole graphics Kitty.
    """
    path = Path(image_path)
    if not path.exists():
        return b""

    data = path.read_bytes()
    encoded = base64.b64encode(data)

    # Chunk size (Kitty recommande <= 4096)
    chunk_size = 4096
    chunks = [encoded[i : i + chunk_size] for i in range(0, len(encoded), chunk_size)]

    out = bytearray()
    # a=T (transmission directe), f=100 (PNG), t=d (disque)
    # On utilise le mode streaming avec m=1 pour les chunks intermédiaires
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        m = 0 if is_last else 1
        header = f"\x1b_Ga=T,m={m};".encode()
        out.extend(header)
        out.extend(chunk)
        out.extend(b"\x1b\\")

    # Afficher avec contrôle : placement à la position curseur
    # s=cols, v=rows (on laisse Kitty ajuster si non spécifié)
    display_cmd = f"\x1b_Gf=100,t=d;a=T;c={max_width}\x1b\\".encode()
    out.extend(display_cmd)

    return bytes(out)


def render_image_sixel(image_path: str | Path, max_width: int = 640) -> bytes:
    """Tente de générer une image Sixel.

    Nécessite img2sixel (libsixel) installé. Retourne un placeholder si
    l'outil n'est pas disponible.
    """
    import shutil
    import subprocess

    if not shutil.which("img2sixel"):
        return b""

    try:
        result = subprocess.run(
            ["img2sixel", "-w", str(max_width), str(image_path)],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return b""


def render_image_placeholder(filename: str) -> str:
    """Génère un placeholder textuel quand le terminal ne supporte pas les images."""
    return f"[image: {filename}]"


def render_image(image_path: str | Path, max_width: int = 640) -> bytes | str:
    """Affiche une image selon le protocole supporté par le terminal.

    Retourne :
    - bytes : séquences d'échappement à écrire sur stdout
    - str : placeholder textuel si aucun protocole n'est supporté
    """
    protocol = get_protocol()
    if protocol == "kitty":
        return render_image_kitty(image_path, max_width)
    if protocol == "sixel":
        return render_image_sixel(image_path, max_width)
    return render_image_placeholder(Path(image_path).name)


def format_image_message(
    sender: str,
    image_url: str,
    filename: str,
    access_token: str,
    homeserver: str,
) -> str:
    """Formate un message image pour affichage dans RichLog.

    Tente de télécharger et rendre l'image. Si le terminal supporte
    un protocole, renvoie le placeholder + l'image sera affichée via
    une méthode spécifique. Sinon, renvoie un placeholder.
    """
    protocol = get_protocol()
    if protocol == "none":
        return f"[dim]{sender}: [image: {filename}][/image][/dim]"

    # Télécharger l'image en arrière-plan
    local_path = download_image(image_url, access_token, homeserver)
    if local_path is None:
        return f"[dim]{sender}: [image: {filename}][/dim]"

    return f"__NERVE_IMAGE__:{local_path}:{filename}"


def is_image_message(body: str) -> bool:
    """Vrai si le body contient notre marqueur d'image."""
    return body.startswith("__NERVE_IMAGE__:")
