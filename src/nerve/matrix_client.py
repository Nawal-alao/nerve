"""Fine couche au-dessus de matrix-nio pour matui.

Cette classe centralise tout ce qui touche au protocole Matrix : connexion,
sync loop, envoi de messages, gestion basique du chiffrement (E2EE) et
vérification par emoji. L'interface Textual ne parle jamais directement à
`nio` — elle passe toujours par ici.
"""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    KeyVerificationEvent,
    KeyVerificationKey,
    KeyVerificationStart,
    LoginResponse,
    MatrixRoom,
    RoomMessageText,
    UploadResponse,
)
from nio.exceptions import LocalProtocolError

from .config import Credentials, decrypt_store, encrypt_store, ensure_store_dir, remove_store

MessageHandler = Callable[[MatrixRoom, RoomMessageText], Awaitable[None]]
# Invitation reçue : (room_id, salle, inviteur)
InviteHandler = Callable[[str, MatrixRoom, str], Awaitable[None]]
# Vérification par emoji : (transaction_id, user_id, device_id, emojis)
# où emojis est une liste de (emoji, description).
SasRequestHandler = Callable[[str, str, str, list[tuple[str, str]]], Awaitable[None]]
# Échec d'envoi (ex. appareils non vérifiés dans un salon chiffré) : (room_id, message)
SendErrorHandler = Callable[[str, str], Awaitable[None]]


@dataclass
class NerveClient:
    creds: Credentials
    client: AsyncClient = field(init=False)
    _sync_task: asyncio.Task | None = field(init=False, default=None)
    on_message: MessageHandler | None = None
    on_invite: InviteHandler | None = None
    on_sas_request: SasRequestHandler | None = None
    on_send_error: SendErrorHandler | None = None
    # État exposé à l'UI (header) : connecting → syncing → online/offline.
    sync_state: str = field(init=False, default="connecting")

    def __post_init__(self) -> None:
        store_path = str(ensure_store_dir())
        config = AsyncClientConfig(
            store_sync_tokens=True,
            encryption_enabled=True,
        )
        self.client = AsyncClient(
            homeserver=self.creds.homeserver,
            user=self.creds.user_id,
            device_id=self.creds.device_id,
            store_path=store_path,
            config=config,
        )
        self.client.access_token = self.creds.access_token
        self.client.user_id = self.creds.user_id
        self._store_loaded = False

        self.client.add_event_callback(self._handle_message, RoomMessageText)
        self.client.add_event_callback(self._handle_invite, InviteMemberEvent)
        self.client.add_to_device_callback(
            self._handle_verification, (KeyVerificationEvent,)
        )

    # ------------------------------------------------------------------
    # Connexion
    # ------------------------------------------------------------------
    @staticmethod
    async def login(homeserver: str, user_id: str, password: str) -> Credentials:
        """Connexion initiale par mot de passe, produit des Credentials
        réutilisables (access token + device id) pour les lancements suivants.
        """
        store_path = str(ensure_store_dir())
        client = AsyncClient(homeserver=homeserver, user=user_id, store_path=store_path)
        resp = await client.login(password, device_name="nerve")
        if not isinstance(resp, LoginResponse):
            await client.close()
            raise RuntimeError(f"Échec de connexion : {resp}")

        creds = Credentials(
            homeserver=homeserver,
            user_id=resp.user_id,
            device_id=resp.device_id,
            access_token=resp.access_token,
        )
        await client.close()
        return creds

    def load_local_store(self) -> None:
        """Déchiffre (si besoin) puis charge les clés E2EE locales.
        Lève decrypt_store()/StoreLockedError quand la clé du store est
        indisponible : l'UI propose alors la restauration par clé de
        récupération."""
        if self.client.olm is None or self._store_loaded:
            return
        # Le store était chiffré au repos : on le restaure avant de lire les
        # clés de session E2EE.
        decrypt_store()
        self.client.load_store()
        self._store_loaded = True

    async def start(self) -> None:
        """Charge les clés de chiffrement locales et démarre la sync loop."""
        self.load_local_store()
        # Un premier sync complet avant de tourner en continu, pour avoir
        # tout de suite la liste des salons peuplée.
        self.sync_state = "syncing"
        await self.client.sync(timeout=30000, full_state=True)
        self.sync_state = "online"
        self._sync_task = asyncio.create_task(self._run_sync_forever())

    async def _run_sync_forever(self) -> None:
        """Boucle de sync en tâche de fond, surveillée pour le header."""
        try:
            await self.client.sync_forever(timeout=30000, full_state=False)
        finally:
            self.sync_state = "offline"

    async def stop(self) -> None:
        if self._sync_task is not None:
            self._sync_task.cancel()
        await self.client.close()
        # Clés de session E2EE protégées au repos après la fermeture.
        encrypt_store()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    async def _send(self, room_id: str, message_type: str, content: dict) -> None:
        """Envoie un événement de salle en appliquant la politique de sécurité.

        On n'ignore PAS les appareils non vérifiés : si le salon est chiffré
        et qu'un contact n'a pas validé son appareil, nio refuse l'envoi
        (LocalProtocolError). On le signale à l'UI plutôt que de transmettre
        à un destinataire potentiellement compromis.
        """
        try:
            await self.client.room_send(
                room_id=room_id,
                message_type=message_type,
                content=content,
            )
        except LocalProtocolError as exc:
            if self.on_send_error is not None:
                await self.on_send_error(room_id, str(exc))
        except Exception as exc:  # network / homeserver
            if self.on_send_error is not None:
                await self.on_send_error(room_id, f"{type(exc).__name__}: {exc}")

    async def send_message(self, room_id: str, body: str) -> None:
        await self._send(
            room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": body},
        )

    async def send_emote(self, room_id: str, body: str) -> None:
        """Commande /me : une action affichée en italique (* nom action)."""
        await self._send(
            room_id,
            "m.room.message",
            {"msgtype": "m.emote", "body": body},
        )

    async def react_to(self, room_id: str, event_id: str, reaction: str) -> None:
        """Commande /react : pose une réaction (annotation) sur un message."""
        await self._send(
            room_id,
            "m.reaction",
            {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": event_id,
                    "key": reaction,
                }
            },
        )

    async def part_room(self, room_id: str, message: str | None = None) -> None:
        """Commande /quit : quitte le salon (message d'adieu optionnel)."""
        if message:
            await self.send_message(room_id, message)
        await self.client.room_leave(room_id)

    async def send_image(self, room_id: str, path: str) -> None:
        """Commande /sendimg : upload une image et l'envoie (chiffrée, comme
        les messages E2EE)."""
        file = Path(path).expanduser()
        if not file.is_file():
            if self.on_send_error is not None:
                await self.on_send_error(room_id, f"Fichier introuvable : {path}")
            return
        mimetype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        size = file.stat().st_size
        try:
            with file.open("rb") as fh:
                resp, decrypt_keys = await self.client.upload(
                    fh,
                    content_type=mimetype,
                    filename=file.name,
                    encrypt=True,
                    filesize=size,
                )
        except Exception as exc:
            if self.on_send_error is not None:
                await self.on_send_error(room_id, f"Upload : {type(exc).__name__}: {exc}")
            return
        if not isinstance(resp, UploadResponse):
            if self.on_send_error is not None:
                await self.on_send_error(room_id, f"Upload refusé : {resp}")
            return
        content = {
            "msgtype": "m.image",
            "body": file.name,
            "info": {"mimetype": mimetype, "size": size},
            "file": {**decrypt_keys, "url": resp.content_uri},
        }
        await self._send(room_id, "m.room.message", content)

    async def logout(self) -> None:
        """Déconnecte de l'appareil : invalide le token côté serveur puis
        efface les identifiants et le store local."""
        try:
            await self.client.logout()
        except Exception:
            pass  # même hors-ligne, on nettoie localement
        await self.client.close()
        self.creds.remove()
        remove_store()

    async def join_room(self, room_id_or_alias: str) -> None:
        await self.client.join(room_id_or_alias)

    async def accept_invite(self, room_id: str) -> None:
        await self.client.join(room_id)

    async def decline_invite(self, room_id: str) -> None:
        await self.client.room_leave(room_id)

    def rooms(self) -> dict[str, MatrixRoom]:
        return self.client.rooms

    async def verify_device_by_emoji(self, user_id: str, device_id: str) -> None:
        """Démarre une vérification interactive par emoji avec un appareil
        donné. Le SAS (Short Authentication String) est confirmé via
        `confirm_short_auth_string` une fois que les deux côtés voient les
        mêmes emojis.
        """
        await self.client.start_key_verification(user_id, device_id)

    async def confirm_sas(self, transaction_id: str) -> None:
        """Confirme que les emojis correspondent (décision humaine)."""
        await self.client.confirm_short_auth_string(transaction_id)

    async def reject_sas(self, transaction_id: str) -> None:
        """Annule la vérification : le SAS ne correspond pas."""
        await self.client.cancel_key_verification(transaction_id, reject=True)

    async def cancel_sas(self, transaction_id: str) -> None:
        """Annule la vérification (abandon de l'utilisateur)."""
        await self.client.cancel_key_verification(transaction_id, reject=False)

    # ------------------------------------------------------------------
    # Callbacks internes (branchés sur nio)
    # ------------------------------------------------------------------
    async def _handle_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        if self.on_message is not None:
            await self.on_message(room, event)

    async def _handle_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        if event.state_key != self.client.user_id:
            return
        if self.on_invite is not None:
            await self.on_invite(room.room_id, room, event.sender)

    async def _handle_verification(self, event: KeyVerificationEvent) -> None:
        # Vérification de la "short auth string" (SAS) : on n'accepte et ne
        # confirme JAMAIS automatiquement. On affiche les emojis à l'écran et
        # on attend une confirmation humaine explicite avant de valider.
        if isinstance(event, KeyVerificationStart):
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas is None:
                return
            await self.client.accept_key_verification(sas.transaction_id)
        elif isinstance(event, KeyVerificationKey):
            # Le SAS est établi : les emojis sont désormais calculables.
            # On les transmet à l'UI pour comparaison, sans confirmer.
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas is None or self.on_sas_request is None:
                return
            device = sas.other_olm_device
            emojis = sas.get_emoji()
            await self.on_sas_request(
                sas.transaction_id, device.user_id, device.id, emojis
            )
        # KeyVerificationMac : rien à faire ici. nio ne vérifie l'appareil
        # que si l'on a (déjà) validé les emojis via confirm_sas().
