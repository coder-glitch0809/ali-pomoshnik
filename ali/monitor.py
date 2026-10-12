"""Monitoring: kim nima ish qilyapti - ishlar ro'yxati, agentlar statistikasi va jonli lenta.

Har bir so'rov - bitta "ish" (job). Ali vazifani agentga topshirsa, agent uchun alohida ish ochiladi.
Ishlar va statistika data/monitor.json da saqlanadi, jonli lenta faqat xotirada.
"""
import json
import logging
import threading
import time
import uuid
from collections import deque
from typing import Callable

from .config import config

log = logging.getLogger("ali.monitor")

PATH = config.data_dir / "monitor.json"
MAX_JOBS = 200
MAX_LOG = 400


def _today() -> str:
    return time.strftime("%Y-%m-%d")


class Monitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: deque[dict] = deque(maxlen=MAX_JOBS)
        self.stats: dict[str, dict] = {}  # agent -> {"total": n, "day": "YYYY-MM-DD", "today": n, "last": "..."}
        self.feed: deque[dict] = deque(maxlen=MAX_LOG)
        self.notify: Callable[[dict], None] = lambda payload: None
        self._load()

    # --- saqlash ---
    def _load(self) -> None:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for job in data.get("jobs", []):
            if job.get("status") == "running":  # server o'chib qolgan
                job["status"] = "error"
                job["end"] = job.get("start")
            self.jobs.append(job)
        self.stats = data.get("stats", {})

    def _save(self) -> None:
        try:
            PATH.write_text(json.dumps({"jobs": list(self.jobs), "stats": self.stats}, ensure_ascii=False),
                            encoding="utf-8")
        except OSError:
            log.exception("monitor.json saqlanmadi")

    # --- ishlar ---
    def start_job(self, agent: str, text: str, source: str) -> str:
        job = {"id": uuid.uuid4().hex[:10], "agent": agent, "text": text[:300], "source": source,
               "start": time.time(), "end": None, "status": "running", "steps": 0}
        with self.lock:
            self.jobs.append(job)
            s = self.stats.setdefault(agent, {"total": 0, "day": _today(), "today": 0})
            if s.get("day") != _today():
                s["day"], s["today"] = _today(), 0
            s["total"] += 1
            s["today"] += 1
            s["last"] = text[:160]
        self.notify({"type": "monitor"})
        return job["id"]

    def step(self, job_id: str) -> None:
        with self.lock:
            for job in reversed(self.jobs):
                if job["id"] == job_id:
                    job["steps"] += 1
                    break

    def finish(self, job_id: str, ok: bool) -> None:
        with self.lock:
            for job in reversed(self.jobs):
                if job["id"] == job_id:
                    job["status"] = "done" if ok else "error"
                    job["end"] = time.time()
                    break
            self._save()
        self.notify({"type": "monitor"})

    # --- jonli lenta ---
    def add_log(self, agent: str, kind: str, text: str) -> None:
        """kind: user | tool | think | answer | error | agent"""
        entry = {"t": time.time(), "agent": agent, "kind": kind, "text": " ".join(text.split())[:400]}
        with self.lock:
            self.feed.append(entry)
        self.notify({"type": "monitor_log", "entry": entry})

    def snapshot(self, team: dict) -> dict:
        """team: {key: {"name", "icon", "description"}} - Ali va barcha agentlar."""
        with self.lock:
            jobs = list(self.jobs)
            agents = []
            for key, info in team.items():
                s = self.stats.get(key, {})
                running = next((j for j in reversed(jobs) if j["agent"] == key and j["status"] == "running"), None)
                agents.append({
                    **info, "key": key,
                    "status": "running" if running else "idle",
                    "since": running["start"] if running else None,
                    "current": running["text"] if running else None,
                    "last": s.get("last", ""),
                    "today": s.get("today", 0) if s.get("day") == _today() else 0,
                    "total": s.get("total", 0),
                })
            return {"agents": agents, "jobs": jobs[-60:][::-1], "feed": list(self.feed)[-200:]}


monitor = Monitor()
