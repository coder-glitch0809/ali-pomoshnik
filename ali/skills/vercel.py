"""Vercel: loyihalar, deploylar holati, xato loglari, qayta deploy.

.env da VERCEL_TOKEN kerak: https://vercel.com/account/tokens -> Create Token.
Jamoa (team) loyihalari uchun VERCEL_TEAM_ID ham yozing.
"""
import httpx

from ..config import config
from . import skill

API = "https://api.vercel.com"


def _req(method: str, path: str, **kw):
    if not config.vercel_token:
        raise RuntimeError("VERCEL_TOKEN yo'q (.env). README -> Vercel bo'limiga qarang.")
    params = kw.pop("params", {})
    if config.vercel_team_id:
        params["teamId"] = config.vercel_team_id
    with httpx.Client(base_url=API, timeout=30, headers={"Authorization": f"Bearer {config.vercel_token}"}) as c:
        r = c.request(method, path, params=params, **kw)
        r.raise_for_status()
        return r.json()


def _ts(ms) -> str:
    import time
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ms / 1000)) if ms else "-"


@skill(
    description="Vercel'dagi barcha loyihalar: nomi, framework, oxirgi deploy holati va manzili.",
    params={"query": {"type": "string", "description": "Nom bo'yicha filtr (ixtiyoriy)"}},
    required=[],
)
def vercel_projects(query: str = "") -> str:
    projects = _req("GET", "/v9/projects", params={"limit": 100}).get("projects", [])
    rows = []
    for p in projects:
        if query and query.lower() not in p["name"].lower():
            continue
        latest = (p.get("latestDeployments") or [{}])[0]
        repo = (p.get("link") or {}).get("repo") or "-"
        rows.append(f"- {p['name']} | {p.get('framework') or '-'} | {latest.get('readyState', '-')} "
                    f"{_ts(latest.get('createdAt'))} | https://{latest.get('url', '-')} | github: {repo}")
    return "\n".join(rows) or "Loyiha topilmadi."


@skill(
    description="Vercel loyihasining oxirgi deploylari (holati: READY / ERROR / BUILDING), commit xabari va manzili.",
    params={"project": {"type": "string", "description": "Vercel loyiha nomi"}},
)
def vercel_deployments(project: str) -> str:
    pid = _req("GET", f"/v9/projects/{project}")["id"]
    deps = _req("GET", "/v6/deployments", params={"projectId": pid, "limit": 10}).get("deployments", [])
    return "\n".join(
        f"- {d['uid']} | {d.get('state') or d.get('readyState')} | {_ts(d.get('created'))} | {d.get('target') or 'preview'} | "
        f"{(d.get('meta') or {}).get('githubCommitMessage', '')[:80]} | https://{d['url']}"
        for d in deps
    ) or "Deploy yo'q."


@skill(
    description="Deploy build loglari (oxirgi qatorlar) - xato sababini topish uchun. deployment - vercel_deployments dagi uid.",
    params={"deployment": {"type": "string", "description": "Deploy ID (dpl_...) yoki manzili"}},
)
def vercel_logs(deployment: str) -> str:
    events = _req("GET", f"/v3/deployments/{deployment}/events", params={"limit": 300, "direction": "backward"})
    lines = [(e.get("payload") or {}).get("text") or e.get("text") or "" for e in (events if isinstance(events, list) else [])]
    lines = [l for l in lines if l][::-1][-120:]
    return "\n".join(lines) or "Log topilmadi."


@skill(
    description="Loyihaning oxirgi production deployini qayta deploy qiladi. Foydalanuvchi tasdiqlaydi.",
    params={"project": {"type": "string", "description": "Vercel loyiha nomi"}},
    dangerous=True,
)
def vercel_redeploy(project: str) -> str:
    pid = _req("GET", f"/v9/projects/{project}")["id"]
    deps = _req("GET", "/v6/deployments", params={"projectId": pid, "limit": 1, "target": "production"}).get("deployments", [])
    if not deps:
        return "Production deploy topilmadi."
    new = _req("POST", "/v13/deployments", json={"name": project, "deploymentId": deps[0]["uid"], "target": "production"})
    return f"Qayta deploy boshlandi: https://{new.get('url')} (holat: {new.get('readyState')})"
