"""Gestion multi-comptes pour shelltrix.

Permet de sauvegarder plusieurs comptes Matrix et de commuter entre eux.
Les identifiants sont stockés dans ~/.config/shelltrix/accounts.json (métadonnées)
et les tokens dans le keyring système.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

from .config import CONFIG_DIR, KEYRING_SERVICE, Credentials

ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"


@dataclass
class AccountInfo:
    """Informations légères d'un compte (sans secrets)."""
    user_id: str
    homeserver: str
    device_id: str
    label: str  # Nom d'affichage (ex: "Alice @ matrix.org")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AccountInfo":
        return cls(**data)


class AccountManager:
    """Gère la liste des comptes sauvegardés."""

    def __init__(self) -> None:
        self._accounts: List[AccountInfo] = []
        self._load()

    def _load(self) -> None:
        """Charge la liste des comptes depuis accounts.json."""
        if not ACCOUNTS_FILE.exists():
            self._accounts = []
            return
        try:
            data = json.loads(ACCOUNTS_FILE.read_text())
            self._accounts = [AccountInfo.from_dict(a) for a in data.get("accounts", [])]
        except (OSError, ValueError, KeyError, TypeError):
            self._accounts = []

    def _save(self) -> None:
        """Persiste la liste des comptes."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"accounts": [a.to_dict() for a in self._accounts]}
        ACCOUNTS_FILE.write_text(json.dumps(data, indent=2))
        ACCOUNTS_FILE.chmod(0o600)

    @property
    def accounts(self) -> List[AccountInfo]:
        return list(self._accounts)

    def count(self) -> int:
        return len(self._accounts)

    def get(self, user_id: str) -> AccountInfo | None:
        """Récupère un compte par user_id."""
        for acc in self._accounts:
            if acc.user_id == user_id:
                return acc
        return None

    def add(self, creds: Credentials) -> AccountInfo:
        """Ajoute un compte à la liste (ou remplace si existe déjà)."""
        # Supprimer l'ancien entry si existe
        self._accounts = [a for a in self._accounts if a.user_id != creds.user_id]
        label = _make_label(creds.user_id, creds.homeserver)
        info = AccountInfo(
            user_id=creds.user_id,
            homeserver=creds.homeserver,
            device_id=creds.device_id,
            label=label,
        )
        self._accounts.append(info)
        self._save()
        return info

    def remove(self, user_id: str) -> None:
        """Retire un compte de la liste (mais pas les creds/keyring)."""
        self._accounts = [a for a in self._accounts if a.user_id != user_id]
        self._save()

    def load_credentials(self, user_id: str) -> Credentials | None:
        """Charge complètement les creds d'un compte (avec token depuis keyring)."""
        acc = self.get(user_id)
        if acc is None:
            return None
        return Credentials.load_for(acc.user_id, acc.homeserver, acc.device_id)


def _make_label(user_id: str, homeserver: str) -> str:
    """Construit un label lisible : @alice — matrix.org."""
    # Extraire le localpart de @alice:matrix.org
    short = user_id
    if ":" in user_id and user_id.startswith("@"):
        short = user_id.split(":", 1)[0]
    # Extraire le domaine de https://matrix.org
    domain = homeserver
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    domain = domain.rstrip("/")
    return f"{short} — {domain}"


# Instance globale
_manager: AccountManager | None = None


def get_manager() -> AccountManager:
    """Récupère l'instance globale du gestionnaire de comptes."""
    global _manager
    if _manager is None:
        _manager = AccountManager()
    return _manager
