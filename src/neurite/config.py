"""Gestion de la configuration et des identifiants persistants de neurite."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken

CONFIG_DIR = Path.home() / ".config" / "neurite"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
STORE_DIR = CONFIG_DIR / "store"
# Vérificateur (scrypt) de la clé de récupération : permet de reconnaître la
# clé sur une machine neuve, sans stocker la clé elle-même.
RECOVERY_FILE = CONFIG_DIR / "recovery.json"

KEYRING_SERVICE = "neurite"
# Clé du trousseau contenant le token d'accès. Le token est un secret au même
# titre qu'un mot de passe : on le conserve dans le trousseau système, jamais
# en clair sur le disque.
_USERNAME_ACCESS_TOKEN = "access_token"

# Clé du trousseau contenant la clé Fernet qui chiffre le store olm au repos.
_USERNAME_STORE_KEY = "store_key"
# Marqueur présent uniquement quand le store est chiffré.
STORE_ENC_MARKER = STORE_DIR / ".neurite-encrypted"


class StoreLockedError(RuntimeError):
    """Le store local est chiffré mais aucune clé exploitable n'est
    disponible : l'utilisateur doit fournir sa clé de récupération."""


@dataclass
class Credentials:
    homeserver: str
    user_id: str
    device_id: str
    access_token: str

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    # Les métadonnées (homeserver, user_id, device_id) ne sont pas sensibles et
    # restent dans credentials.json (chmod 600). Le token d'accès, lui, est un
    # secret : il vit dans le trousseau système (keyring) plutôt qu'en clair.

    def _keyring_username(self) -> str:
        return f"{self.user_id}:{_USERNAME_ACCESS_TOKEN}"

    @classmethod
    def load(cls) -> "Credentials | None":
        if not CREDENTIALS_FILE.exists():
            return None
        data = json.loads(CREDENTIALS_FILE.read_text())

        # 1) Token depuis le trousseau système.
        token: str | None = None
        if data.get("user_id"):
            token = keyring.get_password(
                KEYRING_SERVICE,
                f"{data['user_id']}:{_USERNAME_ACCESS_TOKEN}",
            )

        # 2) Rétro-compatibilité : les anciennes versions stockaient le token
        #    en clair dans credentials.json. On s'en sert comme secours et il
        #    sera migré vers le trousseau au prochain save().
        legacy = data.get("access_token")
        if token is None and legacy:
            token = legacy

        return cls(
            homeserver=data["homeserver"],
            user_id=data["user_id"],
            device_id=data["device_id"],
            access_token=token or "",
        )

    @classmethod
    def load_for(cls, user_id: str, homeserver: str, device_id: str) -> "Credentials | None":
        """Charge les creds pour un compte spécifique (multi-compte)."""
        token = keyring.get_password(
            KEYRING_SERVICE,
            f"{user_id}:{_USERNAME_ACCESS_TOKEN}",
        )
        return cls(
            homeserver=homeserver,
            user_id=user_id,
            device_id=device_id,
            access_token=token or "",
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Métadonnées non sensibles.
        CREDENTIALS_FILE.write_text(
            json.dumps(
                {
                    "homeserver": self.homeserver,
                    "user_id": self.user_id,
                    "device_id": self.device_id,
                },
                indent=2,
            )
        )
        CREDENTIALS_FILE.chmod(0o600)
        # Token dans le trousseau système.
        keyring.set_password(
            KEYRING_SERVICE,
            self._keyring_username(),
            self.access_token,
        )

    def remove(self) -> None:
        """Efface les identifiants persistants (déconnexion)."""
        CREDENTIALS_FILE.unlink(missing_ok=True)
        try:
            keyring.delete_password(KEYRING_SERVICE, self._keyring_username())
        except keyring.errors.PasswordDeleteError:
            pass


def ensure_store_dir() -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    return STORE_DIR


def skip_splash() -> bool:
    """Vrai si l'application doit démarrer sans l'écran de bienvenue.

    Option lisible dans config.json via la clé `skip_splash` (défaut :
    désactivé). N'est pas persistée par neurite : l'utilisateur la pose
    manuellement pour un lancement rapide / scripté."""
    try:
        data = json.loads(CONFIG_DIR.joinpath("config.json").read_text())
        return bool(data.get("skip_splash", False))
    except (OSError, ValueError, TypeError):
        return False


def remove_store() -> None:
    """Supprime le store olm local (déconnexion complète de l'appareil)."""
    shutil.rmtree(STORE_DIR, ignore_errors=True)
    RECOVERY_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Chiffrement au repos du store olm (clés de chiffrement E2EE)
# ---------------------------------------------------------------------------
# nio conserve les clés de session olm/megolm en clair dans sa base SQLite.
# On les chiffre donc au repos : decrypt_store() au démarrage (avant le
# load_store()), encrypt_store() à l'arrêt (après close()). La clé Fernet
# vit dans le trousseau système. Le marqueur n'est posé (resp. retiré) qu'une
# fois toutes les écritures terminées.


def _store_fernet(
    key: str | None = None, *, create: bool = True
) -> Fernet | None:
    """Clé Fernet du store : clé explicite, trousseau, ou génération.

    - `key` fourni (clé de récupération) : on l'utilise telle quelle ;
    - sinon on lit la clé persistée dans le trousseau ;
    - si absente, on en génère une nouvelle uniquement quand `create`
      est vrai (chiffrement à l'arrêt, première création).
    Renvoie None quand aucune clé n'existe et qu'on ne veut pas en créer
    (restauration : l'UI demandera la clé de récupération)."""
    if key is not None:
        return Fernet(key.encode())
    stored = keyring.get_password(KEYRING_SERVICE, _USERNAME_STORE_KEY)
    if stored:
        return Fernet(stored.encode())
    if not create:
        return None
    new_key = Fernet.generate_key()
    keyring.set_password(KEYRING_SERVICE, _USERNAME_STORE_KEY, new_key.decode())
    return Fernet(new_key)


def _enc_store_is_encrypted() -> bool:
    return STORE_ENC_MARKER.exists()


def _enc_rotate(file: Path, transform) -> None:
    """Remplace `file` par sa version transformée, de façon atomique."""
    with tempfile.NamedTemporaryFile(
        dir=str(STORE_DIR), prefix=".neurite-tmp-", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        tmp_path.write_bytes(transform(file.read_bytes()))
        os.replace(tmp_path, file)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Clé de récupération de session
# ---------------------------------------------------------------------------
# La clé de récupération est la clé Fernet du store (soit celle du trousseau,
# soit une nouvelle générée par l'utilisateur). Elle est présentée sous forme
# base64 URL-safe et peut être resaisie sur une autre machine. On ne persiste
# qu'un émpreinte scrypt (salt + hash), jamais la clé elle-même.


def normalize_recovery_key(raw: str) -> str:
    """Nettoie la saisie : ignore les espaces/sauts de ligne et ré-applique
    le padding '=' (base64 url-safe sans caractère particulier)."""
    s = "".join(raw.split())
    s = s.rstrip("=")
    s += "=" * ((-len(s)) % 4)
    return s


def _recovery_digest(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        secret.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32
    )


def recovery_save(secret: str) -> None:
    """Persiste le vérificateur (scrypt) de la clé de récupération pour
    pouvoir la reconnaître sur une machine neuve."""
    normalized = normalize_recovery_key(secret)
    salt = os.urandom(16)
    data = {
        "salt": salt.hex(),
        "hash": _recovery_digest(normalized, salt).hex(),
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RECOVERY_FILE.write_text(json.dumps(data, indent=2))
    RECOVERY_FILE.chmod(0o600)


def recovery_has_verifier() -> bool:
    return RECOVERY_FILE.exists()


def recovery_verify(secret: str) -> bool:
    """Vrai si `secret` correspond au vérificateur persisté."""
    try:
        data = json.loads(RECOVERY_FILE.read_text())
        salt = bytes.fromhex(data["salt"])
        expected = bytes.fromhex(data["hash"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    try:
        digest = _recovery_digest(normalize_recovery_key(secret), salt)
    except ValueError:
        return False
    return hmac.compare_digest(digest, expected)


def reveal_recovery_secret() -> str:
    """Renvoie la clé de récupération du store actif (crée la clé du
    trousseau si elle n'existe pas encore) et en persiste le vérificateur."""
    key = keyring.get_password(KEYRING_SERVICE, _USERNAME_STORE_KEY)
    if key is None:
        key = Fernet.generate_key().decode()
        try:
            keyring.set_password(KEYRING_SERVICE, _USERNAME_STORE_KEY, key)
        except Exception:
            pass  # sans trousseau, la clé reste montrable en session
    secret = normalize_recovery_key(key)
    recovery_save(secret)
    return secret


def regenerate_recovery_secret() -> str:
    """Génère une nouvelle clé de store et en expose la clé de récupération.
    L'ancienne clé de récupération devient invalide (le store sera rechiffré
    avec la nouvelle à l'arrêt)."""
    new_key = Fernet.generate_key().decode()
    try:
        keyring.set_password(KEYRING_SERVICE, _USERNAME_STORE_KEY, new_key)
    except Exception:
        pass  # le trousseau peut être indisponible : la clé reste exploitable
    secret = normalize_recovery_key(new_key)
    recovery_save(secret)
    return secret


def decrypt_store(recovery_key: str | None = None) -> None:
    """Restaure le store en clair s'il était chiffré (appelé avant load_store).

    Sans clé : on utilise celle du trousseau (lève StoreLockedError si elle
    est absente). Avec `recovery_key` : on accepte la clé de récupération,
    on la ré-enregistre dans le trousseau au succès."""
    if not _enc_store_is_encrypted():
        return
    if recovery_key is None:
        fernet = _store_fernet(create=False)
        if fernet is None:
            raise StoreLockedError(
                "The E2EE store is encrypted but its key is missing from the "
                "system keyring. Enter your recovery key to restore it."
            )
    else:
        key = normalize_recovery_key(recovery_key)
        if recovery_has_verifier() and not recovery_verify(key):
            raise StoreLockedError(
                "Invalid recovery key (does not match the saved verifier)."
            )
        try:
            fernet = _store_fernet(key=key)
        except ValueError as exc:  # clé mal formée (mauvaise longueur/caractère)
            raise StoreLockedError(
                "Invalid recovery key (bad format). Check the characters."
            ) from exc
    candidates = [
        p
        for p in STORE_DIR.iterdir()
        if p.is_file() and p != STORE_ENC_MARKER
    ]
    try:
        for file in candidates:
            _enc_rotate(file, fernet.decrypt)
    except InvalidToken as exc:
        raise StoreLockedError(
            "Invalid recovery key (wrong key or corrupted store)."
        ) from exc
    # Tout est déchiffré : on retire le marqueur en dernier.
    STORE_ENC_MARKER.unlink(missing_ok=True)
    if recovery_key is not None:
        # La clé fonctionne : on la ré-enregistre pour les prochains lancements.
        try:
            keyring.set_password(KEYRING_SERVICE, _USERNAME_STORE_KEY, key)
        except Exception:
            pass


def encrypt_store() -> None:
    """Chiffre le store (appelé après close(), à l'arrêt). Clés E2EE protégées au repos."""
    if not STORE_DIR.exists():
        return
    fernet = _store_fernet()
    candidates = [
        p for p in STORE_DIR.iterdir() if p.is_file() and p != STORE_ENC_MARKER
    ]
    for file in candidates:
        _enc_rotate(file, fernet.encrypt)
    # Tout est chiffré : on pose le marqueur en dernier.
    STORE_ENC_MARKER.touch()
