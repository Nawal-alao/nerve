"""Rendu inline des images dans nerve.

Affiche les messages m.image de façon totalement sûre pour Textual : l'image
est décomposée en demi-blocs Unicode (▀) colorés en vraie couleur (truecolor),
écrits comme de simples lignes de texte dans le RichLog — aucune séquence
d'échappement brute sur stdout qui corromprait l'écran plein écran.

Ce rendu fonctionne sur tout terminal supportant la vraie couleur (24 bits),
ce qui inclut la grande majorité des terminaux modernes.

Fallback : affiche un placeholder [image: nom] si le décodage d'image
(Pillow) n'est pas disponible.
"""

from __future__ import annotations

import base64
from pathlib import Path

from .config import CONFIG_DIR

_images_dir = CONFIG_DIR / "images"


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


def render_image_placeholder(filename: str) -> str:
    """Génère un placeholder simple et lisible quand le rendu inline échoue."""
    name = Path(filename).name or "image"
    return f"📷 [dim]Image · {name}[/dim]"


def _has_pillow() -> bool:
    """Vrai si Pillow est disponible pour décoder les images."""
    try:
        import PIL  # noqa: F401

        return True
    except Exception:
        return False


def _rgb_hex(r: int, g: int, b: int) -> str:
    """Convertit des composantes RGB en code couleur hexadécimal Rich."""
    return f"#{r:02x}{g:02x}{b:02x}"


def render_image_textual(image_path: str | Path, max_width_cols: int = 40) -> str | None:
    """Affiche une image en demi-blocs Unicode colorés (▀), sûr pour Textual.

    Chaque cellule terminal affiche 2 rangées d'image : le pixel du haut est
    la couleur de premier plan, celui du bas la couleur d'arrière-plan, via
    le caractère demi-bloc supérieur ▀. Le résultat est une simple chaîne de
    markup Rich, sans séquences d'échappement sur stdout.

    Renvoie None si Pillow est absent, le fichier est illisible ou l'image
    est invalide.
    """
    if not _has_pillow():
        return None
    path = Path(image_path)
    if not path.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
    except Exception:
        return None

    width, height = img.size
    if width <= 0 or height <= 0 or max_width_cols <= 0:
        return None

    scale = max_width_cols / width
    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    px = img.load()

    lines = []
    for row in range(0, new_h, 2):
        cells = []
        bottom_row = min(row + 1, new_h - 1)
        for col in range(new_w):
            tr, tg, tb = px[col, row][:3]
            br, bg, bb = px[col, bottom_row][:3]
            cells.append(f"[{_rgb_hex(tr, tg, tb)} on {_rgb_hex(br, bg, bb)}]▀[/]")
        lines.append("".join(cells))
    return "\n".join(lines)


def render_image(image_path: str | Path, max_width_cols: int = 40) -> str:
    """Rend une image en texte TrueColor sûr pour Textual.

    Retourne toujours une chaîne : le rendu demi-bloc si disponible, sinon
    un placeholder. Plus aucune sortie binaire sur stdout.
    """
    textual = render_image_textual(image_path, max_width_cols)
    if textual is not None:
        return textual
    return render_image_placeholder(Path(image_path).name)


def format_image_message(
    sender: str,
    image_url: str,
    filename: str,
    access_token: str,
    homeserver: str,
) -> str:
    """Formate un message image pour affichage dans RichLog.

    Télécharge l'image en cache ; si le téléchargement réussit, renvoie le
    marqueur interne (sous forme de chemin local à rendre). Sinon, renvoie
    un placeholder textuel.
    """
    local_path = download_image(image_url, access_token, homeserver)
    if local_path is None:
        return f"[dim]{sender}: [image: {filename}][/image][/dim]"

    return f"__NERVE_IMAGE__:{local_path}:{filename}"


def is_image_message(body: str) -> bool:
    """Vrai si le body contient notre marqueur d'image."""
    return body.startswith("__NERVE_IMAGE__:")
