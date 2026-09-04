"""Fixture globale : isole le répertoire de cache SQLite des tests.

Les tests qui instancient `ChatScreen` créent un `MessageCache` (dont le
répertoire par défaut est `~/.config/nerve/cache`). On redirige `CONFIG_DIR`
du module `cache` vers un répertoire temporaire pour que les tests n'écrivent
jamais dans le vrai répertoire de configuration de l'utilisateur.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("nerve.cache.CONFIG_DIR", tmp_path / "config")
    yield
