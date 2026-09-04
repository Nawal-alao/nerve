"""Cache SQLite local des messages de timeline.

Persiste les `TimelineEntry` par salon (dédupliquées par `event_id`) afin de :
  - ne pas perdre l'historique reçu via sync/scrollback à chaque fermeture ;
  - afficher instantanément un salon déjà vu (offline-ish) avant même que le
    scrollback serveur ne revienne.

Le cache est scopé par `user_id` (prêt pour le multi-comptes) et stocké dans
`CONFIG_DIR/cache/`. Les corps de messages étant potentiellement sensibles, le
fichier est créé en 0600.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import CONFIG_DIR
from .formatting import TimelineEntry

_EVENT_COLUMNS = (
    "room_id",
    "event_id",
    "sender",
    "display_name",
    "is_own",
    "time_ms",
    "body",
    "msgtype",
    "has_mention",
    "is_image",
    "image_hint",
    "timestamp",
)


def _cache_dir() -> Path:
    d = CONFIG_DIR / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


class MessageCache:
    """Cache SQLite des messages d'un seul compte."""

    def __init__(self, user_id: str, cache_dir: Path | None = None) -> None:
        # Le user_id (@alice:hs) contient des caractères non-valides pour un nom
        # de fichier ; on les neutralise pour un nom stable et sûr.
        safe = user_id.replace("@", "at_").replace(":", "_").replace("/", "_")
        self.user_id = user_id
        if cache_dir is None:
            cache_dir = _cache_dir()
        self.path = cache_dir / f"{safe}.db"
        new_db = not self.path.exists()
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        if new_db:
            self.path.chmod(0o600)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                user_id TEXT NOT NULL,
                room_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                display_name TEXT NOT NULL,
                is_own INTEGER NOT NULL,
                time_ms INTEGER NOT NULL,
                body TEXT NOT NULL,
                msgtype TEXT NOT NULL,
                has_mention INTEGER NOT NULL,
                is_image INTEGER NOT NULL,
                image_hint TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (user_id, room_id, event_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_room
                ON messages (user_id, room_id, time_ms);
            """
        )
        self._conn.commit()

    def upsert_entries(self, room_id: str, entries: list[TimelineEntry]) -> None:
        """Insère ou remplace les entrées non vides par `event_id`."""
        if not entries:
            return
        sql = (
            "INSERT OR REPLACE INTO messages ("
            + ", ".join(["user_id", *_EVENT_COLUMNS])
            + ") VALUES ("
            + ", ".join(["?"] * (len(_EVENT_COLUMNS) + 1))
            + ")"
        )
        rows = []
        for e in entries:
            if not e.event_id:
                continue
            rows.append(
                (
                    self.user_id,
                    room_id,
                    e.event_id,
                    e.sender,
                    e.display_name,
                    int(e.is_own),
                    e.time_ms,
                    e.body,
                    e.msgtype,
                    int(e.has_mention),
                    int(e.is_image),
                    e.image_hint,
                    e.timestamp,
                )
            )
        self._conn.executemany(sql, rows)
        self._conn.commit()

    def load_entries(self, room_id: str) -> list[TimelineEntry]:
        """Charge les entrées d'un salon, triées par timestamp croissant."""
        rows = self._conn.execute(
            "SELECT " + ", ".join(_EVENT_COLUMNS)
            + " FROM messages WHERE user_id=? AND room_id=? ORDER BY time_ms",
            (self.user_id, room_id),
        ).fetchall()
        return [self._entry_from_row(r) for r in rows]

    @staticmethod
    def _entry_from_row(r: sqlite3.Row) -> TimelineEntry:
        return TimelineEntry(
            sender=r["sender"],
            display_name=r["display_name"],
            is_own=bool(r["is_own"]),
            time_ms=r["time_ms"],
            body=r["body"],
            event_id=r["event_id"],
            msgtype=r["msgtype"],
            has_mention=bool(r["has_mention"]),
            is_image=bool(r["is_image"]),
            image_hint=r["image_hint"],
            timestamp=r["timestamp"],
        )

    def clear_room(self, room_id: str) -> None:
        """Efface les messages mis en cache d'un salon (ex. action clear)."""
        self._conn.execute(
            "DELETE FROM messages WHERE user_id=? AND room_id=?",
            (self.user_id, room_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
