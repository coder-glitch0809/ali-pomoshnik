"""Instagram audit va kuzatuv: profil, postlar (rasmlarini AI ko'radi), joylash chastotasi -> aniq tavsiyalar.

Manbalar: ChatPlace (bot orqali ulangan Instagram: obunachilar, postlar, Virale tahlili) va Instagram Graph API
(token bo'lsa: qamrov, saqlash, ulashish). Kuzatuv: har kuni 21:30 da qisqa holat (obunachi o'zgarishi, post
tanaffusi), har yakshanba 20:00 da to'liq audit. Tarix data/ig_history.json da.
"""
import json
import logging
import time
from datetime import date, datetime, timedelta

import httpx

from .config import config

log = logging.getLogger("ali.instagram_audit")

HISTORY = config.data_dir / "ig_history.json"
DAILY_AT, WEEKLY_AT, WEEKLY_DAY = "21:30", "20:00", 6  # yakshanba
QUERY_WORDS = ("instagram", "инстаграм", "insta", "инста", "profil", "профил")
ACTION_WORDS = ("tahlil", "таҳлил", "тахлил", "analiz", "анализ", "audit", "аудит", "maslahat", "маслахат", "маслаҳат",
                "to'g'rila", "togirla", "тўғрила", "тогрила", "kuzat", "кузат", "statistik", "статистик")

AUDIT_TASK = """Sen kuchli Instagram strateg va targetologsan. Egamning Instagram profilini audit qil va ANIQ, amaliy
tavsiyalar ber. Egam: targetolog va tashqi reklama agentligi egasi (hajmli harflar, bannerlar, vizitkalar); profil
asosan shu 2 yo'nalishga ishlashi kerak (o'qituvchilik - kamdan-kam). Biriktirilgan rasmlar - oxirgi postlarning
muqovalari: dizayn, matn o'qilishi, birinchi kadr, brend izchilligini KO'RIB baholang.

Ma'lumot:
{data}

FAQAT JSON qaytar:
{{"score": 0-100, "summary": "3-4 gapda umumiy holat",
  "strengths": ["..."],
  "problems": [{{"problem": "aniq muammo", "why": "nega muhim", "fix": "aniq nima qilish"}}],
  "profile_fixes": ["bio, nik, avatar, highlights, havola bo'yicha aniq o'zgartirishlar (tayyor matn bilan)"],
  "content_fixes": ["format, hook, muqova, caption, CTA bo'yicha"],
  "posting": "chastota va vaqt bo'yicha xulosa va tavsiya",
  "next_7_days": ["1-kun: ...", "..."]}}"""


def _bots() -> list[dict]:
    from . import mcp_client
    if not mcp_client.connected("chatplace"):
        return []
    try:
        bots = json.loads(mcp_client.call_tool("chatplace", "bots_list", {}, None))
    except (ValueError, RuntimeError):
        return []
    return [b for b in bots if (b.get("platform") or {}).get("label") == "instagram"]


def _call(tool: str, args: dict):
    from . import mcp_client
    raw = mcp_client.call_tool("chatplace", tool, args, None)  # to'liq JSON (kesilmasin)
    if raw.startswith("XATO"):
        raise RuntimeError(raw[6:200])
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def collect() -> list[dict]:
    """Har bir Instagram akkaunt bo'yicha ma'lumot: obunachilar, postlar, chastota, Virale tahlili."""
    accounts = []
    for b in _bots():
        acc = {"bot_id": b["id"], "username": b.get("username", ""), "name": b.get("name", "")}
        try:
            info = _call("bots_get", {"botId": b["id"]})
            acc["followers"] = info.get("followersCount") if isinstance(info, dict) else None
        except RuntimeError:
            acc["followers"] = None
        try:
            media = _call("automations_triggers_list_instagram_media", {"botId": b["id"]})
        except RuntimeError:
            media = []
        media = sorted(media if isinstance(media, list) else [], key=lambda m: m.get("timestamp", 0), reverse=True)
        acc["posts"] = [{"date": datetime.fromtimestamp(m["timestamp"]).strftime("%Y-%m-%d %H:%M %a") if m.get("timestamp") else "",
                         "caption": (m.get("caption") or "")[:300], "link": m.get("permalink", ""),
                         "thumb": m.get("mediaUrl", "")} for m in media[:30]]
        ts = [m["timestamp"] for m in media if m.get("timestamp")]
        now = time.time()
        acc["frequency"] = {
            "posts_7d": sum(1 for t in ts if now - t < 7 * 86400),
            "posts_30d": sum(1 for t in ts if now - t < 30 * 86400),
            "days_since_last": round((now - max(ts)) / 86400, 1) if ts else None,
            "hours": sorted({datetime.fromtimestamp(t).strftime("%H:00") for t in ts[:20]}),
            "empty_captions": sum(1 for m in media[:20] if not (m.get("caption") or "").strip()),
        }
        for tool in ("virale_dashboard", "virale_recommendations"):
            try:
                acc[tool] = _call(tool, {"botId": b["id"]})
            except RuntimeError as e:
                acc[tool] = f"(hali tayyor emas: {e})"
        accounts.append(acc)
    return accounts


def _thumbs(accounts: list[dict], limit: int = 8) -> list[str]:
    from . import ingest
    paths = []
    for acc in accounts:
        for p in acc["posts"][:limit]:
            if not p.get("thumb"):
                continue
            try:
                r = httpx.get(p["thumb"], timeout=20, follow_redirects=True)
                if r.status_code == 200 and r.content:
                    paths.append(str(ingest.save_upload(f"ig_{acc['username'].lstrip('@')}.jpg", r.content)))
            except httpx.HTTPError:
                continue
    return paths[:limit]


def audit() -> dict:
    """To'liq audit: ma'lumot + postlar rasmlari -> Pro ilova tahlili. Natija xotira va Obsidian'ga ham yoziladi."""
    from . import local_ai
    from .memory import memory
    from .service import _ask_json
    accounts = collect()
    if not accounts:
        raise RuntimeError("Instagram ma'lumoti yo'q: ChatPlace'da Instagram bot ulanganini tekshiring")
    snapshot(accounts)
    data = []
    for a in accounts:
        hist = _history().get(a["username"], [])
        data.append({k: v for k, v in a.items() if k != "bot_id"} | {
            "posts": [{k: v for k, v in p.items() if k != "thumb"} for p in a["posts"]],
            "followers_history": hist[-14:]})
    images = _thumbs(accounts)
    ready = local_ai.connected() if local_ai.access() is True else []
    prompt = AUDIT_TASK.format(data=json.dumps(data, ensure_ascii=False)[:40000])
    if images and ready:
        got = local_ai.ask_pro(prompt, 900, None, images)
        raw = got[1] if got else ""
        result = json.loads(raw[raw.index("{"):raw.rindex("}") + 1]) if raw else _ask_json(prompt, ready, 900)
    else:
        result = _ask_json(prompt, ready, 900)
    result["accounts"] = [{"username": a["username"], "followers": a["followers"], **a["frequency"]} for a in accounts]
    memory.add_knowledge(f"[kontent] Instagram audit {date.today().isoformat()}", report(result))
    return result


def report(r: dict) -> str:
    lines = []
    for a in r.get("accounts", []):
        lines.append(f"📊 {a['username']}: {a.get('followers') or '?'} obunachi · 7 kunda {a.get('posts_7d')} post · "
                     f"30 kunda {a.get('posts_30d')} · oxirgi post {a.get('days_since_last')} kun oldin")
    lines.append(f"\n⭐ Baho: {r.get('score', '?')}/100\n{r.get('summary', '')}")
    if r.get("strengths"):
        lines += ["\n✅ Yaxshi tomonlar:"] + [f"• {s}" for s in r["strengths"]]
    if r.get("problems"):
        lines.append("\n🔧 To'g'rilash kerak:")
        for i, p in enumerate(r["problems"], 1):
            lines.append(f"{i}. {p.get('problem')}\n   Nega: {p.get('why')}\n   ➜ {p.get('fix')}")
    for key, title in (("profile_fixes", "👤 Profil (bio, avatar, highlights)"), ("content_fixes", "🎬 Kontent")):
        if r.get(key):
            lines += [f"\n{title}:"] + [f"• {s}" for s in r[key]]
    if r.get("posting"):
        lines.append(f"\n🕒 Joylash: {r['posting']}")
    if r.get("next_7_days"):
        lines += ["\n📅 Keyingi 7 kun:"] + [f"• {s}" for s in r["next_7_days"]]
    return "\n".join(lines)


# --- kuzatuv ---
def _history() -> dict:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def snapshot(accounts: list[dict] | None = None) -> list[str]:
    """Kunlik holatni yozadi va o'zgarishlarni qaytaradi (obunachilar, post tanaffusi)."""
    accounts = accounts if accounts is not None else collect()
    hist, notes, today = _history(), [], date.today().isoformat()
    for a in accounts:
        rows = [r for r in hist.get(a["username"], []) if r["date"] != today]
        prev = rows[-1] if rows else None
        rows.append({"date": today, "followers": a["followers"], "posts_30d": a["frequency"]["posts_30d"]})
        hist[a["username"]] = rows[-120:]
        if prev and a["followers"] is not None and prev.get("followers") is not None:
            diff = a["followers"] - prev["followers"]
            notes.append(f"{a['username']}: {a['followers']} obunachi ({'+' if diff >= 0 else ''}{diff} {prev['date']} dan beri)")
        gap = a["frequency"]["days_since_last"]
        if gap is not None and gap >= 3:
            notes.append(f"⚠️ {a['username']}: oxirgi post {gap:.0f} kun oldin - bugun kontent joylang (/kontent)")
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    return notes


def is_query(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in QUERY_WORDS) and any(w in low for w in ACTION_WORDS)


_last = {"daily": "", "weekly": ""}


def tick(notify) -> None:
    """Kontent reja tsiklidan har 30 soniyada chaqiriladi: kunlik holat va haftalik audit."""
    now = datetime.now()
    today = now.date().isoformat()
    if now.strftime("%H:%M") >= DAILY_AT and _last["daily"] != today:
        _last["daily"] = today
        try:
            notes = snapshot()
            if notes:
                notify("📈 Instagram kunlik holat:\n" + "\n".join(notes))
        except Exception as e:
            log.warning("Instagram kunlik holat olinmadi: %s", e)
    if now.weekday() == WEEKLY_DAY and now.strftime("%H:%M") >= WEEKLY_AT and _last["weekly"] != today:
        _last["weekly"] = today
        try:
            notify("🔍 Haftalik Instagram audit:\n\n" + report(audit())[:3800])
        except Exception as e:
            log.warning("Haftalik audit bajarilmadi: %s", e)
