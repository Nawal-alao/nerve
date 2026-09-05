"""Tests pour le cache SQLite MessageCache (messages de timeline).

Cible la persistance / restauration des TimelineEntry par salon et la
déduplication par event_id, sans toucher au vrai répertoire de config.
"""

from __future__ import annotations

from shelltrix.cache import MessageCache
from shelltrix.formatting import TimelineEntry


def _entry(
    event_id: str,
    sender: str = "@alice:hs",
    time_ms: int = 1000,
    body: str = "bonjour",
) -> TimelineEntry:
    return TimelineEntry(
        sender=sender,
        display_name="Alice",
        is_own=False,
        time_ms=time_ms,
        body=body,
        event_id=event_id,
        msgtype="m.text",
        has_mention=False,
        timestamp="00:01",
    )


class TestMessageCache:
    def test_empty_load(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        assert cache.load_entries("!r:hs") == []
        cache.close()

    def test_upsert_and_load(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!r:hs", [_entry("$a", time_ms=2000), _entry("$b", time_ms=1000)])
        entries = cache.load_entries("!r:hs")
        assert [e.event_id for e in entries] == ["$b", "$a"]  # tri chronologique
        cache.close()

    def test_upsert_dedup_by_event_id(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!r:hs", [_entry("$a", body="v1")])
        cache.upsert_entries("!r:hs", [_entry("$a", body="v2")])
        entries = cache.load_entries("!r:hs")
        assert len(entries) == 1
        assert entries[0].body == "v2"  # OR REPLACE
        cache.close()

    def test_empty_event_id_skipped(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!r:hs", [_entry("")])
        assert cache.load_entries("!r:hs") == []
        cache.close()

    def test_rooms_isolated(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!a:hs", [_entry("$1")])
        cache.upsert_entries("!b:hs", [_entry("$2", body="autre")])
        entries = cache.load_entries("!a:hs")
        assert [e.event_id for e in entries] == ["$1"]
        cache.close()

    def test_accounts_isolated(self, tmp_path) -> None:
        alice = MessageCache("@alice:hs", cache_dir=tmp_path)
        bob = MessageCache("@bob:hs", cache_dir=tmp_path)
        alice.upsert_entries("!r:hs", [_entry("$1")])
        assert bob.load_entries("!r:hs") == []
        assert alice.load_entries("!r:hs") != []
        alice.close()
        bob.close()

    def test_persists_across_reopen(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!r:hs", [_entry("$a")])
        cache.close()
        reopened = MessageCache("@me:hs", cache_dir=tmp_path)
        entries = reopened.load_entries("!r:hs")
        assert [e.event_id for e in entries] == ["$a"]
        reopened.close()

    def test_clear_room(self, tmp_path) -> None:
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries("!a:hs", [_entry("$1")])
        cache.upsert_entries("!b:hs", [_entry("$2")])
        cache.clear_room("!a:hs")
        assert cache.load_entries("!a:hs") == []
        assert cache.load_entries("!b:hs") != []
        cache.close()


class TestMessageCacheSearch:
    def _setup(self, tmp_path):
        cache = MessageCache("@me:hs", cache_dir=tmp_path)
        cache.upsert_entries(
            "!a:hs",
            [
                _entry("$1", time_ms=1000, body="Bonjour Alice"),
                _entry("$2", time_ms=2000, body="Vous cherchez quoi ?"),
                _entry("$3", time_ms=3000, body="alice vint enfin"),
            ],
        )
        cache.upsert_entries("!b:hs", [_entry("$4", time_ms=1500, body="Bonjour Bob")])
        return cache

    def test_empty_query(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        assert cache.search_messages("") == []
        cache.close()

    def test_case_insensitive(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        results = cache.search_messages("BONJOUR")
        assert len(results) == 2  # Bonjour Alice + Bonjour Bob
        cache.close()

    def test_ordered_newest_first(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        results = cache.search_messages("alice")
        ids = [e.event_id for e in results]
        # $3 (alice vint, t=3000) avant $1 (Bonjour Alice, t=1000)
        assert ids == ["$3", "$1"]
        cache.close()

    def test_scope_room(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        results = cache.search_messages("BONJOUR", room_id="!a:hs")
        assert [e.event_id for e in results] == ["$1"]
        cache.close()

    def test_limit(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        assert len(cache.search_messages("a", limit=1)) == 1
        cache.close()

    def test_search_with_room_returns_room(self, tmp_path) -> None:
        cache = self._setup(tmp_path)
        hits = cache.search_with_room("BONJOUR")
        pairs = sorted((room, e.event_id) for room, e in hits)
        assert pairs == [("!a:hs", "$1"), ("!b:hs", "$4")]
        cache.close()


class TestMessageCacheImportable:
    def test_module_imports(self) -> None:
        from shelltrix import cache  # noqa: F401
