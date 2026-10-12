"""Xotira: SQLite bazasi.

Jadvallar:
  facts      - uzoq muddatli xotira (foydalanuvchi haqida faktlar, afzalliklar)
  messages   - barcha suhbatlar jurnali (tarix, tahlil uchun)
  reminders  - eslatmalar
"""
import sqlite3
import threading
from datetime import datetime

from .config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL,
    due_at     TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Memory:
    def __init__(self, path=config.db_path):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _exec(self, sql: str, params: tuple = ()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    # --- Faktlar ---
    def set_fact(self, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO facts(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key.strip().lower(), value.strip(), _now()),
        )

    def delete_fact(self, key: str) -> bool:
        return self._exec("DELETE FROM facts WHERE key=?", (key.strip().lower(),)).rowcount > 0

    def all_facts(self) -> dict[str, str]:
        rows = self._exec("SELECT key, value FROM facts ORDER BY key").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # --- Suhbat jurnali ---
    def log_message(self, session_id: str, role: str, content: str) -> None:
        self._exec(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
            (session_id, role, content, _now()),
        )

    # --- Bilimlar bazasi (o'rganilgan mavzular) ---
    def add_knowledge(self, topic: str, content: str) -> int:
        return self._exec(
            "INSERT INTO knowledge(topic, content, created_at) VALUES(?,?,?)", (topic.strip(), content.strip(), _now())
        ).lastrowid

    def search_knowledge(self, query: str, limit: int = 5) -> list[sqlite3.Row]:
        words = [w for w in query.lower().split() if len(w) > 2] or [query.lower()]
        where = " OR ".join("lower(topic || ' ' || content) LIKE ?" for _ in words)
        return self._exec(
            f"SELECT * FROM knowledge WHERE {where} ORDER BY id DESC LIMIT ?", (*[f"%{w}%" for w in words], limit)
        ).fetchall()

    def knowledge_topics(self) -> list[str]:
        return [r["topic"] for r in self._exec("SELECT DISTINCT topic FROM knowledge ORDER BY id DESC").fetchall()]

    # --- Eslatmalar ---
    def add_reminder(self, text: str, due_at: datetime) -> int:
        return self._exec(
            "INSERT INTO reminders(text, due_at) VALUES(?,?)", (text, due_at.isoformat(timespec="seconds"))
        ).lastrowid

    def due_reminders(self) -> list[sqlite3.Row]:
        return self._exec("SELECT * FROM reminders WHERE done=0 AND due_at<=?", (_now(),)).fetchall()

    def pending_reminders(self) -> list[sqlite3.Row]:
        return self._exec("SELECT * FROM reminders WHERE done=0 ORDER BY due_at").fetchall()

    def mark_done(self, reminder_id: int) -> None:
        self._exec("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))


memory = Memory()
