"""Render (render.com): xizmatlar holati, deploylar, loglar, qayta deploy.

.env da RENDER_API_KEY kerak: https://dashboard.render.com/u/settings#api-keys -> Create API Key.
Ruxsatlar -> Ulanishlar -> Render oynasidan ham kiritiladi.
"""
import httpx

from ..config import config
from . import skill

API = "https://api.render.com/v1"


def _req(method: str, path: str, **kw):
    if not config.render_api_key:
        raise RuntimeError("RENDER_API_KEY yo'q: Ruxsatlar -> Ulanishlar -> Render")
    with httpx.Client(base_url=API, timeout=30, headers={"Authorization": f"Bearer {config.render_api_key}",
                                                         "Accept": "application/json"}) as c:
        r = c.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}


def _service(name: str) -> dict:
    """Nom yoki ID (srv-...) bo'yicha xizmat."""
    for row in _req("GET", "/services", params={"limit": 100}):
        s = row.get("service", row)
        if name in (s["id"], s["name"]) or name.lower() in s["name"].lower():
            return s
    raise RuntimeError(f"Render xizmati topilmadi: {name}")


@skill(
    description="Render'dagi barcha xizmatlar (web, worker, cron, static): nomi, turi, holati (to'xtatilganmi), manzili, repo.",
    params={"query": {"type": "string", "description": "Nom bo'yicha filtr (ixtiyoriy)"}},
    required=[],
)
def render_services(query: str = "") -> str:
    rows = []
    for row in _req("GET", "/services", params={"limit": 100}):
        s = row.get("service", row)
        if query and query.lower() not in s["name"].lower():
            continue
        url = (s.get("serviceDetails") or {}).get("url") or "-"
        rows.append(f"- {s['name']} ({s['id']}) | {s.get('type')} | {'to‘xtatilgan' if s.get('suspended') == 'suspended' else 'faol'}"
                    f" | {url} | repo: {s.get('repo') or '-'} ({s.get('branch') or '-'})")
    return "\n".join(rows) or "Xizmat topilmadi."


@skill(
    description="Render xizmatining oxirgi deploylari: holati (live / build_failed / update_in_progress), commit, vaqti.",
    params={"service": {"type": "string", "description": "Xizmat nomi yoki ID (srv-...)"}},
)
def render_deploys(service: str) -> str:
    s = _service(service)
    rows = []
    for row in _req("GET", f"/services/{s['id']}/deploys", params={"limit": 10}):
        d = row.get("deploy", row)
        commit = (d.get("commit") or {}).get("message", "").split("\n")[0][:80]
        rows.append(f"- {d['id']} | {d.get('status')} | {(d.get('finishedAt') or d.get('createdAt') or '')[:16]} | {commit}")
    return f"{s['name']}:\n" + ("\n".join(rows) or "Deploy yo'q.")


@skill(
    description="Render xizmatining oxirgi loglari (xato sababini topish uchun).",
    params={"service": {"type": "string", "description": "Xizmat nomi yoki ID"},
            "limit": {"type": "integer", "description": "Nechta qator (standart 100)"}},
    required=["service"],
)
def render_logs(service: str, limit: int = 100) -> str:
    s = _service(service)
    data = _req("GET", "/logs", params={"ownerId": s["ownerId"], "resource": s["id"], "limit": min(limit, 300),
                                        "direction": "backward"})
    lines = [f"{l.get('timestamp', '')[:19]} {l.get('message', '')}" for l in data.get("logs", [])][::-1]
    return "\n".join(lines)[-12000:] or "Log topilmadi."


@skill(
    description="Render xizmatini qayta deploy qiladi (oxirgi commit bilan). Foydalanuvchi tasdiqlaydi.",
    params={"service": {"type": "string", "description": "Xizmat nomi yoki ID"},
            "clear_cache": {"type": "boolean", "description": "Build keshini tozalab deploy qilish"}},
    required=["service"],
    dangerous=True,
)
def render_deploy(service: str, clear_cache: bool = False) -> str:
    s = _service(service)
    d = _req("POST", f"/services/{s['id']}/deploys", json={"clearCache": "clear" if clear_cache else "do_not_clear"})
    return f"{s['name']}: deploy boshlandi ({d.get('id')}, holat: {d.get('status')}). render_deploys bilan kuzating."


@skill(
    description="Render xizmatini to'xtatish (suspend) yoki qayta yoqish (resume). Foydalanuvchi tasdiqlaydi.",
    params={"service": {"type": "string", "description": "Xizmat nomi yoki ID"},
            "action": {"type": "string", "enum": ["suspend", "resume"], "description": "suspend - to'xtatish, resume - yoqish"}},
    dangerous=True,
)
def render_power(service: str, action: str) -> str:
    if action not in ("suspend", "resume"):
        return "action: suspend yoki resume"
    s = _service(service)
    _req("POST", f"/services/{s['id']}/{action}")
    return f"{s['name']}: {'to‘xtatildi' if action == 'suspend' else 'qayta yoqildi'}."
