"""Tests pour la reconnexion automatique (backoff exponentiel).

Vérifie le contrat du `_run_sync_forever()` de NeuriteClient : une panne
réseau (sync() qui lève) ne doit pas faire tomber la tâche pour toujours
— elle passe en état "offline"/"reconnecting", attend, puis retente ; un
sync réussi repasse l'état à "online" et remet le backoff à zéro.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neurite.config import Credentials
from neurite.matrix_client import NeuriteClient


@pytest.mark.asyncio
async def test_retries_and_recovers_after_failure() -> None:
    """Après des échecs successifs, le sync finit par réussir : l'état
    repasse en "online" et la boucle continue."""
    calls = 0

    async def flaky_sync(**kwargs) -> object:
        nonlocal calls
        calls += 1
        # échec réseau les 2 premiers appels, puis succès
        if calls <= 2:
            raise ConnectionError("connection reset")
        return object()

    creds = Credentials("hs", "@u:hs", "dev", "token")
    with patch("neurite.matrix_client.AsyncClient") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.sync = AsyncMock(side_effect=flaky_sync)
        client_inst.next_batch = "abc"
        client_inst.add_event_callback = MagicMock()
        client_inst.add_to_device_callback = MagicMock()
        client_inst.rooms = {}

        nc = NeuriteClient(creds)
        nc._ever_connected = True

        async def run() -> None:
            await nc._run_sync_forever()

        task = asyncio.create_task(run())
        # Laisser la boucle tourner assez longtemps pour passer 2 échecs
        # (backoff 1s + 2s) puis un succès.
        await asyncio.sleep(3.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert nc.sync_state == "online"
        assert calls >= 3


@pytest.mark.asyncio
async def test_offline_when_never_connected() -> None:
    """Tant qu'aucun sync n'a réussi, un échec expose l'état 'offline'."""
    async def always_fail(**kwargs) -> object:
        raise ConnectionError("down")

    creds = Credentials("hs", "@u:hs", "dev", "token")
    with patch("neurite.matrix_client.AsyncClient") as mock_client_cls:
        client_inst = mock_client_cls.return_value
        client_inst.sync = AsyncMock(side_effect=always_fail)
        client_inst.add_event_callback = MagicMock()
        client_inst.add_to_device_callback = MagicMock()

        nc = NeuriteClient(creds)
        nc._ever_connected = False  # jamais connecté

        # Premier appel direct : l'exception est avalée par la boucle.
        async def run() -> None:
            await nc._run_sync_forever()

        task = asyncio.create_task(run())
        # backoff 1s → l'état reste "offline" puis on annule
        await asyncio.sleep(1.2)
        state = nc.sync_state
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert state == "offline"
