"""SQLite memory (T16): inventory (part id -> quantity), preferences (budget, printer, level, name) and rejected
choices. It round-trips UserContext, which is what a run's spec.user is filled from."""

import json
import sqlite3
from pathlib import Path

from backend.contracts.runner import runs_root
from backend.contracts.spec import UserContext

SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (part_id TEXT PRIMARY KEY, qty INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rejections (pos INTEGER PRIMARY KEY, text TEXT NOT NULL);
"""
PREFERENCES = ("budget_usd", "printer", "level", "name")


def default_path() -> Path:
    return runs_root() / "memory.sqlite3"


class MemoryStore:
    """One connection per call, so it is safe from FastAPI's worker threads."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or default_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def load(self) -> UserContext:
        with self._connect() as db:
            owned = dict(
                db.execute("SELECT part_id, qty FROM inventory ORDER BY part_id")
            )
            prefs = {
                k: json.loads(v)
                for k, v in db.execute("SELECT key, value FROM preferences")
            }
            rejected = [
                t for (t,) in db.execute("SELECT text FROM rejections ORDER BY pos")
            ]
        return UserContext(owned=owned, rejected=rejected, **prefs)

    def save(self, user: UserContext) -> UserContext:
        """Replace everything with `user` in one transaction; zero quantities are dropped."""
        with self._connect() as db:
            db.execute("DELETE FROM inventory")
            db.execute("DELETE FROM preferences")
            db.execute("DELETE FROM rejections")
            db.executemany(
                "INSERT INTO inventory VALUES (?, ?)",
                [(pid, qty) for pid, qty in user.owned.items() if qty > 0],
            )
            db.executemany(
                "INSERT INTO preferences VALUES (?, ?)",
                [(k, json.dumps(getattr(user, k))) for k in PREFERENCES],
            )
            db.executemany(
                "INSERT INTO rejections VALUES (?, ?)", enumerate(user.rejected)
            )
        return self.load()
