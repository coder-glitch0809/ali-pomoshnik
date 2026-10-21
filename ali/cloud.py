"""Firebase (Firestore) - Ali xotirasining bulutdagi nusxasi.

Xotira kompyuterda tez ishlaydi (data/ali.db), bu modul esa har daqiqada yangi yozuvlarni Firestore'ga yuboradi:
  ali_messages   - barcha yozishmalar va agentlar ishi (har bir qurilmadan: "{qurilma}-{id}")
  ali_facts      - faktlar (qurilmalar o'rtasida ikki tomonlama: kompyuter <-> Render)
  ali_knowledge  - o'rganilgan bilimlar (ikki tomonlama)
  ali_agents     - agentlar sozlamasi va tajribasi (agents/*.md)
Firestore qoidalari mijozlarga yopiq (firebase/firestore.rules) - faqat server admin kaliti bilan kiradi.

Kalit: Firebase Console -> Project settings -> Service accounts -> "Generate new private key" (JSON).
Saytda: Ruxsatlar -> Ulanishlar -> Firebase. Render'da: FIREBASE_CREDENTIALS_JSON muhit o'zgaruvchisi.
"""
import hashlib
import json
import logging
import os
import platform
import threading
import time

from .config import config

log = logging.getLogger("ali.cloud")

KEY_FILE = config.data_dir / "firebase-key.json"
STATE = config.data_dir / "cloud_state.json"
INTERVAL = 60
BATCH = 400

_app = None
_db = None
_lock = threading.Lock()
status = {"enabled": False, "last_sync": 0.0, "error": "", "pushed": 0, "pulled": 0}


def _credentials() -> dict | None:
    raw = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
    if raw:
        return json.loads(raw)
    if KEY_FILE.exists():
        return json.loads(KEY_FILE.read_text(encoding="utf-8"))
    return None


def configured() -> bool:
    return bool(os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()) or KEY_FILE.exists()


def instance() -> str:
    """Qurilma nomi - har qurilmaning xabar ID lari to'qnashmasin."""
    return "render" if os.environ.get("RENDER") else (platform.node() or "pc").lower()


def client():
    global _app, _db
    with _lock:
        if _db is None:
            creds = _credentials()
            if not creds:
                raise RuntimeError("Firebase kaliti yo'q")
            import firebase_admin
            from firebase_admin import credentials, firestore
            _app = firebase_admin.initialize_app(credentials.Certificate(creds), name="ali-cloud")
            _db = firestore.client(app=_app)
        return _db


def reset() -> None:
    """Kalit almashtirilganda qayta ulanish uchun."""
    global _app, _db
    with _lock:
        if _app is not None:
            import firebase_admin
            firebase_admin.delete_app(_app)
        _app = _db = None


def validate(text: str) -> dict:
    """Service account JSON ni tekshiradi va Firestore'ga ulanib ko'radi."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("Bu JSON emas. Firebase'dan yuklab olingan kalit faylining to'liq matnini joylang.") from None
    if data.get("type") != "service_account" or not data.get("private_key") or not data.get("project_id"):
        raise ValueError("Bu service account kaliti emas (Project settings -> Service accounts -> Generate new private key).")
    if config.firebase_project_id and data["project_id"] != config.firebase_project_id:
        raise ValueError(f"Bu kalit boshqa loyihaniki ({data['project_id']}). Kerakli loyiha: {config.firebase_project_id}.")
    import firebase_admin
    from firebase_admin import credentials, firestore
    app = firebase_admin.initialize_app(credentials.Certificate(data), name=f"ali-check-{time.time_ns()}")
    try:
        firestore.client(app=app).collection("ali_meta").document("check").set({"at": time.time(), "from": instance()})
    except Exception as e:
        raise ValueError(f"Firestore'ga yozib bo'lmadi: {str(e)[:200]}. Firestore Database yoqilganini tekshiring.") from None
    finally:
        firebase_admin.delete_app(app)
    return data


# --- holat ---
def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")


def _hash(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()[:20]


# --- sinxronlash ---
def _commit(db, writes: list[tuple[str, str, dict]]) -> None:
    for i in range(0, len(writes), BATCH):
        batch = db.batch()
        for coll, doc, data in writes[i:i + BATCH]:
            batch.set(db.collection(coll).document(doc), data)
        batch.commit()


def _changed(db, collection: str, since: float):
    from google.cloud.firestore_v1.base_query import FieldFilter
    return db.collection(collection).where(filter=FieldFilter("at", ">", since)).stream()


def sync_once() -> dict:
    from . import agents
    from .memory import memory

    db, state, me = client(), _state(), instance()
    pushed = pulled = 0

    # 1) Yangi xabarlar (faqat yuborish - to'liq arxiv bulutda)
    last = state.get("messages", 0)
    rows = memory._exec("SELECT id, session_id, role, content, created_at FROM messages WHERE id>? ORDER BY id LIMIT 2000",
                        (last,)).fetchall()
    if rows:
        _commit(db, [("ali_messages", f"{me}-{r['id']}", {**dict(r), "device": me}) for r in rows])
        state["messages"] = rows[-1]["id"]
        pushed += len(rows)

    # 2) Faktlar - ikki tomonlama (kalit bo'yicha)
    local = memory.all_facts()
    sent = state.setdefault("facts", {})
    writes = [("ali_facts", _hash(k), {"key": k, "value": v, "device": me, "at": time.time()})
              for k, v in local.items() if sent.get(k) != _hash(v)]
    if writes:
        _commit(db, writes)
        sent.update({w[2]["key"]: _hash(w[2]["value"]) for w in writes})
        pushed += len(writes)
    # Faqat oxirgi tekshiruvdan keyin o'zgarganlarini o'qiymiz (Firestore bepul o'qish limitini tejash)
    pull_from, now = state.get("pulled_at", 0), time.time()
    for doc in _changed(db, "ali_facts", pull_from - 120):
        d = doc.to_dict()
        if d.get("key") and d.get("device") != me and local.get(d["key"]) != d.get("value"):
            memory.set_fact(d["key"], d.get("value", ""))
            sent[d["key"]] = _hash(d.get("value", ""))
            pulled += 1

    # 3) Bilimlar - ikki tomonlama (mavzu + matn bo'yicha)
    last_k = state.get("knowledge", 0)
    rows = memory._exec("SELECT id, topic, content, created_at FROM knowledge WHERE id>? ORDER BY id", (last_k,)).fetchall()
    if rows:
        _commit(db, [("ali_knowledge", _hash(r["topic"], r["content"]),
                      {"topic": r["topic"], "content": r["content"], "created_at": r["created_at"], "device": me,
                       "at": time.time()}) for r in rows])
        state["knowledge"] = rows[-1]["id"]
        pushed += len(rows)
    for doc in _changed(db, "ali_knowledge", pull_from - 120):
        d = doc.to_dict()
        if d.get("device") == me or not d.get("topic"):
            continue
        kid = memory.add_knowledge(d["topic"], d.get("content", ""))  # takror bo'lsa qo'shilmaydi
        if kid > state.get("knowledge", 0):
            state["knowledge"] = kid  # bulutdan kelganini qayta yubormaymiz
            pulled += 1
    state["pulled_at"] = now

    # 4) Agentlar va ularning tajribasi (faqat yuborish - zaxira nusxa)
    sent_a = state.setdefault("agents", {})
    writes = []
    for a in agents.load().values():
        md = a.to_markdown()
        if sent_a.get(a.key) != _hash(md):
            writes.append(("ali_agents", a.key, {"key": a.key, "name": a.name, "markdown": md, "device": me, "at": time.time()}))
            sent_a[a.key] = _hash(md)
    if writes:
        _commit(db, writes)
        pushed += len(writes)

    _save_state(state)
    status.update(last_sync=time.time(), error="", pushed=status["pushed"] + pushed, pulled=status["pulled"] + pulled)
    if pushed or pulled:
        log.info("Firebase: %s ta yuborildi, %s ta olindi", pushed, pulled)
    return {"pushed": pushed, "pulled": pulled}


def start() -> None:
    """Fon sinxronlash (kalit bo'lsa). Internet yo'q bo'lsa - keyingi safar davom etadi, hech narsa yo'qolmaydi."""
    if getattr(start, "_started", False):
        return
    start._started = True

    def loop():
        time.sleep(15)
        while True:
            if configured():
                status["enabled"] = True
                try:
                    sync_once()
                except Exception as e:
                    status["error"] = str(e)[:300]
                    log.warning("Firebase sinxronlash xatosi: %s", e)
            else:
                status["enabled"] = False
            time.sleep(INTERVAL)

    threading.Thread(target=loop, daemon=True, name="firebase-sync").start()
