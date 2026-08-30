#!/usr/bin/env python3
"""Migration one-shot: matui -> nerve (renommage du projet).

Copie la configuration et les secrets persistés de l'ancien identifiant
technique "matui" vers le nouveau "nerve", SANS rien supprimer de
l'ancien emplacement tant que l'utilisateur n'a pas validé.

Ce script est sûr (non destructif) tant qu'on n'utilise pas --force-delete :
  - le dossier ~/.config/matui est copié (pas déplacé) vers ~/.config/nerve ;
  - les secrets du trousseau sont relus sous le service "matui" et réécrits
    sous le service "nerve" (mêmes clés/valeurs, nouveau nom de service) ;
  - le marqueur d'encryption au repos, s'il existe, est copié/renommé de
    .matui-encrypted vers .nerve-encrypted dans le store copié.

Les identifiants migrés (KEYRING_SERVICE, CONFIG_DIR, STORE_ENC_MARKER)
doivent correspondre exactement à ce que config.py utilisera une fois le
renommage fait (étape 2 du chantier de renommage).

Usage:
    python scripts/migrate_matui_to_nerve.py           # copie + résumé
    python scripts/migrate_matui_to_nerve.py --status  # ne fait que rapporter
    python scripts/migrate_matui_to_nerve.py --force-delete-old
        # suppression de l'ANCIEN dossier + anciens secrets (seulement après
        # avoir vérifié que l'app fonctionne avec la config migrée !)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import keyring

# Identifiants techniques de l'ANCIENNE identité ("matui"). Ce script est
# un outil one-shot de migration : il référence l'ancien chemin/service
# explicitement et ne dépend PAS du package (renommé en "nerve") pour être
# exécutable même après le renommage du codebase.
OLD_SERVICE = "matui"
NEW_SERVICE = "nerve"
OLD_DIR = Path.home() / ".config" / "matui"
NEW_DIR = Path.home() / ".config" / "nerve"

# Usernames keyring utilisés par l'app : la clé du store (plate) et le
# token d'accès (sous "<user_id>:access_token").
_USERNAME_STORE_KEY = "store_key"
_USERNAME_ACCESS_TOKEN = "access_token"


def _keyring_usernames(credentials: dict) -> set[str]:
    """Les identifiants (usernames keyring) effectivement utilisés par l'app.

    Le token d'accès est stocké sous `<user_id>:access_token` (via
    _keyring_username). La clé du store, elle, est plate : "store_key".
    On balaie donc le username du credential + la clé du store."""
    users = {_USERNAME_STORE_KEY}
    user_id = credentials.get("user_id")
    if user_id:
        users.add(f"{user_id}:{_USERNAME_ACCESS_TOKEN}")
    return users


def _report_status() -> None:
    print("== État actuel de la migration ==")
    print(f"  ancien dossier  : {OLD_DIR}  (existe: {OLD_DIR.exists()})")
    print(f"  nouveau dossier : {NEW_DIR}  (existe: {NEW_DIR.exists()})")
    for user in _keyring_usernames(_load_credentials()):
        old = keyring.get_password(OLD_SERVICE, user)
        new = keyring.get_password(NEW_SERVICE, user)
        print(f"  keyring '{user}': matui={'present' if old else 'absent'} / "
              f"nerve={'present' if new else 'absent'}")
    marker_old = OLD_DIR / "store" / ".matui-encrypted"
    marker_new = NEW_DIR / "store" / ".nerve-encrypted"
    print(f"  marqueur encrypt  : .matui-encrypted existe={marker_old.exists()}")
    print(f"                    : .nerve-encrypted existe={marker_new.exists()}")


def _load_credentials() -> dict:
    if not (OLD_DIR / "credentials.json").exists():
        return {}
    try:
        return json.loads((OLD_DIR / "credentials.json").read_text())
    except (OSError, ValueError):
        return {}


def migrate(force_delete: bool = False) -> None:
    # 1) Copier le dossier de config (jamais supprimer l'original d'office).
    if OLD_DIR.exists():
        tgz_bak = None
        NEW_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(OLD_DIR, NEW_DIR, dirs_exist_ok=True,
                        copy_function=shutil.copy2)
        print(f"[1/4] dossier config copié : {OLD_DIR} -> {NEW_DIR}")
    else:
        print("[1/4] ancien dossier absent, rien à copier "
              f"(config déjà migrée ?). ({OLD_DIR})")

    # 2) Migrer la clé du store + le token d'accès vers le service "nerve".
    migrated = []
    for user in _keyring_usernames(_load_credentials()):
        secret = keyring.get_password(OLD_SERVICE, user)
        if secret is None:
            continue
        # On ne réécrit que si le service cible ne l'a pas déjà (idempotent).
        if keyring.get_password(NEW_SERVICE, user) is None:
            keyring.set_password(NEW_SERVICE, user, secret)
        migrated.append(user)
    if migrated:
        print(f"[2/4] secrets migrés (service '{OLD_SERVICE}' -> "
              f"'{NEW_SERVICE}'): {', '.join(migrated)}")
    else:
        print("[2/4] aucun secret à migrer (déjà migré ou absent).")

    # 3) Marqueur d'encryption au repos : .matui-encrypted -> .nerve-encrypted.
    marker_src = OLD_DIR / "store" / ".matui-encrypted"
    marker_dst = NEW_DIR / "store" / ".nerve-encrypted"
    if marker_src.exists():
        marker_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(marker_src, marker_dst)
        # On retire l'ancien marqueur du dossier COPIÉ uniquement (pas l'orig.)
        copied_old = NEW_DIR / "store" / ".matui-encrypted"
        copied_old.unlink(missing_ok=True)
        print(f"[3/4] marqueur encrypt copié/renommé -> {marker_dst}")
    else:
        print("[3/4] pas de marqueur .matui-encrypted à migrer "
              "(store non chiffré au repos).")

    # 4) Résumé + confirmation avant la moindre suppression.
    print("\n=== Résumé de la migration ===")
    print(f"   nouveau dossier Nerve : {NEW_DIR}")
    print(f"   secrets keyring migrés : {', '.join(migrated) or 'aucun'}")
    print(f"   marqueur encrypt       : {'migré' if marker_src.exists() else 'n/a'}")

    if force_delete:
        _delete_old()
    else:
        print("\nL'ANCIEN dossier/config 'matui' est conservé intact.")
        print("Rien n'a été supprimé. Vérifie que l'app fonctionne avec la")
        print("config migrée (lancement sans re-login), puis si besoin:")
        print("    python scripts/migrate_matui_to_nerve.py --force-delete-old")


def _delete_old() -> None:
    """Supprime l'ancien dossier de config et les secrets keyring 'matui'.
    DESTRUCTIF — à n'exécuter qu'après validation de la config migrée."""
    ans = input("Supprimer définitivement ~/.config/matui et les secrets "
                "keyring 'matui' ? [y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        print("Annulé — rien n'a été supprimé.")
        return
    # Les usernames keyring sont déduits de credentials.json : on les lit
    # AVANT de supprimer le dossier, sinon le service 'matui' conserverait
    # le token d'accès (clé déduite du user_id) en orphelin.
    users = _keyring_usernames(_load_credentials())
    if OLD_DIR.exists():
        shutil.rmtree(OLD_DIR)
        print(f"[ok] dossier supprimé : {OLD_DIR}")
    for user in users:
        try:
            keyring.delete_password(OLD_SERVICE, user)
            print(f"[ok] secret keyring supprimé : '{OLD_SERVICE}/{user}'")
        except keyring.errors.PasswordDeleteError:
            pass
    print("Ancien identifiant 'matui' purgé (dossier + secrets).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", action="store_true",
                    help="Rapporte l'état sans rien modifier.")
    ap.add_argument("--force-delete-old", action="store_true",
                    help="Supprime l'ancien dossier 'matui' + secrets keyring"
                         " après copie (destructif).")
    args = ap.parse_args()

    if args.status:
        _report_status()
    else:
        migrate(force_delete=args.force_delete_old)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrompu.")
