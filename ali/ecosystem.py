"""Ali ekotizimi: Ali - bosh vazir (egasi - prezident). Agentlarni ishga oladi, baholaydi, rag'batlantiradi va jazolaydi.

Ishga olish: «yangi agent kerak: …» yoki «… uchun agent ol» - AI agent tavsifini (vazifa, vositalar, ko'rsatma, o'rganish
mavzulari) tuzadi, Ali uni jamoaga qo'shadi va egasiga xabar beradi.
Baholash (har kuni 21:00): har agentga 0-100 ball (evolution.health: xatolar, bilim, o'rganish, vositalar).
  - ball >= 75 - rag'bat (ogohlantirishlar soni kamayadi);
  - ball < 50 - JAZO, ogohlantirish soni +1:
      1-ogohlantirish: agent ko'rsatmasiga rasmiy ogohlantirish va xatolari yoziladi;
      2-ogohlantirish: Murabbiy majburiy qayta o'qitadi (rivojlantiradi);
      3-ogohlantirish: egasiga ISHDAN BO'SHATISH taklifi - faqat tasdiq bilan (agent o'chirilmaydi, zaxiraga olinadi).
Hisobot: /ekotizim.
"""
import json
import logging
import re
import time
from datetime import date, datetime

from .config import config

log = logging.getLogger("ali.ecosystem")

STATE = config.data_dir / "ecosystem.json"
REVIEW_AT = "21:00"
GOOD, BAD = 75, 50
PROTECTED = {"murabbiy", "dasturchi"}  # jamoani boshqaradiganlar - bo'shatilmaydi
HIRE = re.compile(r"(yangi|янги)\s+agent|agent\S*\s+(qo['ʻ‘]?sh|қўш|ol\b|ол\b|yolla|ёлла|kerak|керак)|"
                  r"(agent|агент)\S*\s+(ishga\s+ol|ишга\s+ол)", re.I)

SPEC = """Sen Ali'ning kadrlar bo'limisan. Egasi (targetolog, tashqi reklama agentligi egasi, informatika o'qituvchisi)
quyidagi ehtiyoj uchun YANGI agent so'radi:
<<<{need}>>>

Mavjud agentlar (takrorlama): {team}
Mavjud vositalar (faqat shulardan tanla, 4-15 ta): {tools}

FAQAT JSON qaytar:
{{"key": "lotin_kichik_harf_pastki_chiziq", "name": "Lavozim nomi", "icon": "bitta emoji",
  "description": "1-2 gapda aniq vazifasi (Ali vazifa topshirishda shunga qaraydi)",
  "tools": ["..."], "learn": ["3-5 ta o'rganish mavzusi"],
  "prompt": "Agentning to'liq ko'rsatmasi (o'zbekcha): rol, ish tartibi (raqamli qadamlar), sifat qoidalari, qachon qaysi vosita"}}"""


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"agents": {}, "last_review": ""}


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def is_hire(text: str) -> bool:
    return bool(HIRE.search(text or ""))


def hire(need: str, brain, ready: list[str]) -> str:
    """Yangi agentni ishga oladi (AI tavsif tuzadi, Ali jamoaga qo'shadi)."""
    from .service import _ask_json
    from .skills.agent_admin import create_agent
    team = ", ".join(f"{a.key} ({a.name})" for a in brain.agents.values())
    tools = ", ".join(sorted(k for k, s in brain.registry.items() if not s.dangerous or k.startswith(("instagram_", "video_"))))
    try:
        spec = _ask_json(SPEC.format(need=need[:1500], team=team, tools=tools[:6000]), ready, 300)
    except (ValueError, RuntimeError) as e:
        return f"⚠️ Agent tavsifi tuzilmadi: {e}"
    key = re.sub(r"[^a-z0-9_]", "", str(spec.get("key", "")).lower())[:30]
    if not key or key in brain.agents:
        return f"⚠️ Agent kaliti noto'g'ri yoki band: «{key}». Ehtiyojni aniqroq yozing."
    spec_tools = [t for t in spec.get("tools", []) if t in brain.registry or t == "web_search"]
    result = create_agent(key, str(spec.get("name", key))[:60], str(spec.get("icon", "🤖"))[:4],
                          str(spec.get("description", ""))[:400], spec_tools or ["web_search", "search_knowledge"],
                          str(spec.get("prompt", ""))[:8000], [str(x) for x in spec.get("learn", [])][:6])
    brain.reload_agents()
    state = _state()
    state["agents"][key] = {"strikes": 0, "hired": date.today().isoformat(), "history": ["ishga olindi"]}
    _save(state)
    log.info("Yangi agent ishga olindi: %s", key)
    return (f"🤝 {result}\nVazifasi: {spec.get('description', '')}\nVositalari: {', '.join(spec_tools) or '-'}\n"
            f"O'rganadi: {', '.join(spec.get('learn', [])[:5])}\nAli unga mos vazifalarni o'zi topshiradi.")


def review(brain, notify=None, confirm=None) -> str:
    """Kunlik baholash: rag'bat va jazo. confirm(name, args) -> bool - ishdan bo'shatish uchun egasining tasdig'i."""
    from . import evolution
    state = _state()
    lines, fire = [], []
    for key, a in list(brain.agents.items()):
        if key in ("18-agent",):
            continue
        rec = state["agents"].setdefault(key, {"strikes": 0, "history": []})
        h = evolution.health(brain.registry, key, brain.agents)
        score, issues = h["score"], h.get("issues", [])
        rec["score"] = score
        if score >= GOOD:
            if rec["strikes"]:
                rec["strikes"] -= 1
                rec["history"].append(f"{date.today()}: rag'bat - ogohlantirish kamaydi ({score} ball)")
            lines.append(f"🏅 {a.icon} {a.name}: {score} ball")
        elif score < BAD:
            rec["strikes"] += 1
            reason = "; ".join(issues[:3]) or "past natija"
            rec["history"].append(f"{date.today()}: JAZO - {rec['strikes']}-ogohlantirish ({score} ball): {reason}")
            lines.append(f"⚠️ {a.icon} {a.name}: {score} ball - {rec['strikes']}-ogohlantirish ({reason})")
            if rec["strikes"] == 1:
                evolution.improve(brain.registry, key, lessons=[
                    f"RASMIY OGOHLANTIRISH ({date.today()}): ishing past baholandi ({score}/100) - {reason}. "
                    "Xatolarni takrorlama, vositalarni to'g'ri ishlat, bilmasang - ochiq ayt."])
            elif rec["strikes"] == 2:
                try:
                    evolution.run_cycle_for(brain, key, {})
                    lines.append(f"   🎓 Murabbiy {a.name}ni majburiy qayta o'qitdi")
                except Exception as e:
                    log.warning("Majburiy o'qitish bajarilmadi %s: %s", key, e)
            elif rec["strikes"] >= 3 and key not in PROTECTED:
                fire.append((key, a, reason))
        else:
            lines.append(f"• {a.icon} {a.name}: {score} ball")
    for key, a, reason in fire:
        ok = bool(confirm and confirm("fire_agent", {"Agent": f"{a.icon} {a.name}",
                                                       "Sabab": f"3 marta past baho: {reason}",
                                                       "Natija": "agent jamoadan chiqariladi (zaxirada saqlanadi)"}))
        if ok:
            from . import agents
            evolution.backup(key)  # agents/_history ga zaxira - kerak bo'lsa qaytariladi
            agents.delete(key)
            brain.reload_agents()
            state["agents"][key]["history"].append(f"{date.today()}: ishdan bo'shatildi (egasi tasdiqladi)")
            lines.append(f"🚪 {a.name} ishdan bo'shatildi")
        else:
            state["agents"][key]["strikes"] = 2  # tasdiqlanmadi - yana bir imkoniyat
            lines.append(f"🙏 {a.name} bo'shatilmadi - oxirgi imkoniyat berildi")
    state["last_review"] = date.today().isoformat()
    _save(state)
    text = "🏛 Ekotizim - kunlik baholash:\n" + "\n".join(lines)
    if notify and (fire or any("⚠️" in l for l in lines)):
        notify(text[:3800])
    return text


def report(brain) -> str:
    state = _state()["agents"]
    rows = []
    for key, a in brain.agents.items():
        rec = state.get(key, {})
        rows.append(f"{a.icon} {a.name}: {rec.get('score', '?')} ball, ogohlantirish {rec.get('strikes', 0)}/3"
                    + (f" · {rec['history'][-1]}" if rec.get("history") else ""))
    return "🏛 Ali ekotizimi (prezident - siz, bosh vazir - Ali):\n\n" + "\n".join(rows) + \
        "\n\n75+ ball - rag'bat, 50 dan past - jazo: 1) ogohlantirish 2) majburiy qayta o'qitish 3) bo'shatish taklifi (tasdiq bilan)."


def tick(brain, notify, confirm) -> None:
    """Avtopilotdan chaqiriladi: kuniga bir marta 21:00 da baholash."""
    if datetime.now().strftime("%H:%M") >= REVIEW_AT and _state().get("last_review") != date.today().isoformat():
        try:
            review(brain, notify, confirm)
        except Exception:
            log.exception("Ekotizim baholashi bajarilmadi")
