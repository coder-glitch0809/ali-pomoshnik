"""Xotira: SQLite bazasi.

Jadvallar:
  facts      - uzoq muddatli xotira (foydalanuvchi haqida faktlar, afzalliklar)
  messages   - barcha suhbatlar jurnali (tarix, tahlil uchun)
  reminders  - eslatmalar
"""
import difflib
import re
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
CREATE TABLE IF NOT EXISTS vault_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


# Xotiraning o'qiladigan nusxasi: loyiha ichidagi xotira/ papkasi (asl baza - data/ali.db)
JOURNAL_DIR = config.data_dir.parent / "xotira"
JOURNAL_README = """# Ali xotirasi

Bu papka Ali xotirasining o'qiladigan nusxasi (Markdown). Asl xotira: `data/ali.db` (SQLite).

- `suhbatlar/YYYY-MM-DD.md` - har kungi barcha yozishmalar (siz, Ali, agentlar ishi)
- Faktlar va o'rganilgan bilimlar - `data/ali.db` (saytda: Vault · Xotira bo'limi)
- Agentlarning tajribasi va saboqlari - `agents/*.md` (Tajriba bo'limi), eski nusxalar - `data/`

Shu papkani va `data/` ni zaxira (backup) qilsangiz, Ali hech narsani unutmaydi.
"""
_journal_lock = threading.Lock()


def journal(role: str, content: str) -> None:
    """Har bir xabar kunlik Markdown faylga ham yoziladi - xotira aniq va ko'rinadigan joyda bo'lsin."""
    try:
        day = datetime.now().strftime("%Y-%m-%d")
        folder = JOURNAL_DIR / "suhbatlar"
        who = {"user": "👤 Siz", "assistant": "🧠 Ali"}.get(role, "🤖 " + role.replace("agent:", "Agent: "))
        with _journal_lock:
            folder.mkdir(parents=True, exist_ok=True)
            readme = JOURNAL_DIR / "README.md"
            if not readme.exists():
                readme.write_text(JOURNAL_README, encoding="utf-8")
            path = folder / f"{day}.md"
            with path.open("a", encoding="utf-8") as f:
                if f.tell() == 0:
                    f.write(f"# Suhbatlar · {day}\n")
                f.write(f"\n### {datetime.now().strftime('%H:%M:%S')} · {who}\n\n{content.strip()}\n")
    except OSError:
        pass  # jurnal - qo'shimcha nusxa; asl xotira bazada saqlangan


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
        journal(role, content)

    def recall(self, question: str, min_ratio: float = 0.9, scan: int = 3000) -> dict | None:
        """Avval aynan shunday (yoki deyarli shunday) savol berilgan bo'lsa - o'shanda berilgan javob.
        {question, answer, at} yoki None."""
        q = _norm(question)
        if len(q) < 8:
            return None
        rows = self._exec("SELECT id, session_id, content, created_at FROM messages WHERE role='user' "
                          "ORDER BY id DESC LIMIT ?", (scan,)).fetchall()
        best = None
        for r in rows:
            ratio = difflib.SequenceMatcher(None, q, _norm(r["content"])).ratio()
            if ratio >= min_ratio and (best is None or ratio > best[0]):
                best = (ratio, r)
                if ratio == 1.0:
                    break
        if not best:
            return None
        r = best[1]
        answer = self._exec("SELECT content, created_at FROM messages WHERE session_id=? AND id>? AND role='assistant' "
                            "ORDER BY id LIMIT 1", (r["session_id"], r["id"])).fetchone()
        if not answer or not answer["content"].strip() or answer["content"].startswith(("⚠", "Xato")):
            return None
        return {"question": r["content"], "answer": answer["content"], "at": answer["created_at"]}

    def relevant_knowledge(self, query: str, prefix: str = "", limit: int = 6, scan: int = 3000) -> list[dict]:
        """Savolga eng mos bilimlar (mazmuni bilan): so'zlar qancha ko'p mos kelsa, shuncha yuqori.
        prefix - faqat shu agent bilimlari ("[kontent] ")."""
        words = {w for w in _norm(query).split() if len(w) > 3}
        if not words:
            return []
        stems = {w[:6] for w in words}  # o'zbekcha qo'shimchalar uchun so'z o'zagi
        sql = "SELECT topic, content, created_at FROM knowledge"
        args: tuple = ()
        if prefix:
            sql += " WHERE substr(topic,1,?)=?"
            args = (len(prefix), prefix)
        rows = self._exec(sql + " ORDER BY id DESC LIMIT ?", (*args, scan)).fetchall()
        scored = []
        for r in rows:
            text = _norm(r["topic"] + " " + r["content"])
            score = sum(2 if s in _norm(r["topic"]) else 1 for s in stems if s in text)
            if score:
                scored.append((score, dict(r)))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def stats(self) -> dict:
        one = lambda sql: self._exec(sql).fetchone()[0]
        return {"messages": one("SELECT count(*) FROM messages WHERE role IN ('user','assistant')"),
                "agent_tasks": one("SELECT count(*) FROM messages WHERE role LIKE 'agent:%'"),
                "facts": one("SELECT count(*) FROM facts"), "knowledge": one("SELECT count(*) FROM knowledge"),
                "first": one("SELECT min(created_at) FROM messages") or ""}

    # --- Bilimlar bazasi (o'rganilgan mavzular) ---
    def recent_messages(self, session_id: str, limit: int = 80) -> list[dict]:
        rows = self._exec("SELECT id, role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                          (session_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def add_knowledge(self, topic: str, content: str) -> int:
        existing = self._exec("SELECT id FROM knowledge WHERE topic=? AND content=? LIMIT 1",
                              (topic.strip(), content.strip())).fetchone()
        if existing:
            return existing["id"]
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

    def agent_knowledge_summary(self, key: str) -> dict:
        prefix = f"[{key}] "
        rows = self._exec("SELECT topic, created_at FROM knowledge WHERE substr(topic,1,?)=? ORDER BY id DESC",
                          (len(prefix), prefix)).fetchall()
        return {"count": len(rows), "latest": [dict(r) for r in rows[:3]]}

    # Unified, read-only view over the original records; no copies of chat history.
    VAULT_SQL = """
        SELECT 'note:' || id AS id, 'inbox' AS folder, title, content, created_at AS updated_at FROM vault_notes
        UNION ALL SELECT 'fact:' || key, 'identity', key, value, updated_at FROM facts
        UNION ALL SELECT 'knowledge:' || id,
          CASE WHEN topic LIKE '[yangiliklar] %' THEN 'news' ELSE 'knowledge' END,
          topic, content, created_at FROM knowledge
        UNION ALL SELECT 'message:' || id, 'chats', role || ' · ' || created_at,
          content, created_at FROM messages
        UNION ALL SELECT 'reminder:' || id, 'reminders', text,
          text || char(10) || 'Vaqti: ' || due_at || char(10) || CASE WHEN done=1 THEN 'Bajarilgan' ELSE 'Kutilmoqda' END,
          due_at FROM reminders
    """

    def vault_list(self, query: str = '', folder: str = '', offset: int = 0, limit: int = 80) -> dict:
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        where = " WHERE (?='' OR folder=?) AND (title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')"
        args = (folder, folder, pattern, pattern)
        base = f"FROM ({self.VAULT_SQL})"
        total = self._exec('SELECT count(*) ' + base + where, args).fetchone()[0]
        rows = self._exec('SELECT id,folder,title,updated_at ' + base + where + ' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?',
                          (*args, limit, offset)).fetchall()
        counts = self._exec('SELECT folder,count(*) AS n ' + base + ' GROUP BY folder').fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "counts": {r['folder']: r['n'] for r in counts}}

    def vault_detail(self, record_id: str) -> dict | None:
        row = self._exec(f"SELECT * FROM ({self.VAULT_SQL}) WHERE id=?", (record_id,)).fetchone()
        return dict(row) if row else None

    def add_vault_note(self, title: str, content: str) -> str:
        row = self._exec('INSERT INTO vault_notes(title,content,created_at) VALUES(?,?,?)',
                         (title.strip(), content.strip(), _now()))
        return f"note:{row.lastrowid}"

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
