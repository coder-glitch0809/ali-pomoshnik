"""GitHub: repozitoriylar, fayllar, commitlar, issue/PR, GitHub Actions holati, klonlash.

.env da GITHUB_TOKEN kerak: https://github.com/settings/tokens -> Fine-grained token
(Repository access: All repositories; Permissions: Contents, Issues, Pull requests, Actions, Metadata - Read and write).
"""
import base64
import subprocess
from functools import lru_cache

import httpx

from ..config import config
from . import skill

API = "https://api.github.com"


def _client() -> httpx.Client:
    if not config.github_token:
        raise RuntimeError("GITHUB_TOKEN yo'q (.env). README -> GitHub bo'limiga qarang.")
    return httpx.Client(base_url=API, timeout=30, headers={
        "Authorization": f"Bearer {config.github_token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })


def _get(path: str, **params):
    with _client() as c:
        r = c.get(path, params=params)
        if r.status_code == 404:
            raise RuntimeError(f"Topilmadi: {path}")
        r.raise_for_status()
        return r.json()


@lru_cache(maxsize=1)
def _login() -> str:
    return _get("/user")["login"]


def _repo(repo: str) -> str:
    repo = repo.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    return repo if "/" in repo else f"{_login()}/{repo}"


@skill(
    description="GitHub'dagi barcha repozitoriylaringiz (oxirgi yangilanganlari birinchi). query - nom/tavsif bo'yicha filtr.",
    params={"query": {"type": "string", "description": "Filtr (ixtiyoriy), masalan 'trade'"}},
    required=[],
)
def github_repos(query: str = "") -> str:
    repos = _get("/user/repos", per_page=100, sort="updated", affiliation="owner,collaborator,organization_member")
    rows = []
    for r in repos:
        text = f"{r['full_name']} {r.get('description') or ''}".lower()
        if query and query.lower() not in text:
            continue
        rows.append(f"- {r['full_name']}{' 🔒' if r['private'] else ''} | {r.get('language') or '-'} | "
                    f"{r['updated_at'][:10]} | {r.get('description') or ''}")
    return "\n".join(rows) or "Repozitoriy topilmadi."


@skill(
    description="Repozitoriy haqida: tavsif, oxirgi commitlar, ochiq issue/PR soni, GitHub Actions (CI) oxirgi natijalari.",
    params={"repo": {"type": "string", "description": "egasi/nomi yoki faqat nomi"}},
)
def github_repo(repo: str) -> str:
    name = _repo(repo)
    info = _get(f"/repos/{name}")
    commits = _get(f"/repos/{name}/commits", per_page=8)
    try:
        runs = _get(f"/repos/{name}/actions/runs", per_page=5).get("workflow_runs", [])
    except Exception:
        runs = []
    lines = [
        f"{info['full_name']} ({'private' if info['private'] else 'public'}) - {info.get('description') or ''}",
        f"Til: {info.get('language')}, branch: {info['default_branch']}, ochiq issue+PR: {info['open_issues_count']}, "
        f"yulduz: {info['stargazers_count']}, sayt: {info.get('homepage') or '-'}",
        "Oxirgi commitlar:",
        *[f"  {c['sha'][:7]} {c['commit']['author']['date'][:10]} {c['commit']['message'].splitlines()[0]}" for c in commits],
    ]
    if runs:
        lines.append("GitHub Actions:")
        lines += [f"  {r['name']}: {r['status']}/{r.get('conclusion')} ({r['created_at'][:16]})" for r in runs]
    return "\n".join(lines)


@skill(
    description="GitHub repozitoriydagi papka ro'yxati yoki fayl mazmuni (path bo'sh - ildiz papka).",
    params={
        "repo": {"type": "string", "description": "egasi/nomi yoki nomi"},
        "path": {"type": "string", "description": "Fayl yoki papka yo'li"},
        "ref": {"type": "string", "description": "Branch/commit (ixtiyoriy)"},
    },
    required=["repo"],
)
def github_read(repo: str, path: str = "", ref: str = "") -> str:
    data = _get(f"/repos/{_repo(repo)}/contents/{path.strip('/')}", **({"ref": ref} if ref else {}))
    if isinstance(data, list):
        return "\n".join(f"{'📁' if d['type'] == 'dir' else '📄'} {d['path']}" for d in data)
    if data.get("encoding") == "base64":
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return text if len(text) < 15000 else text[:15000] + "\n... (qisqartirildi)"
    return f"Fayl juda katta yoki binar: {data.get('download_url')}"


@skill(
    description="Repozitoriyning issue va pull requestlari.",
    params={
        "repo": {"type": "string", "description": "egasi/nomi yoki nomi"},
        "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Holat (standart open)"},
    },
    required=["repo"],
)
def github_issues(repo: str, state: str = "open") -> str:
    items = _get(f"/repos/{_repo(repo)}/issues", state=state, per_page=30)
    return "\n".join(
        f"- #{i['number']} {'[PR] ' if 'pull_request' in i else ''}{i['title']} ({i['state']}, {i['updated_at'][:10]})"
        for i in items
    ) or "Yo'q."


@skill(
    description="GitHub repozitoriyda yangi issue (vazifa/xato yozuvi) ochadi. Foydalanuvchi tasdiqlaydi.",
    params={
        "repo": {"type": "string", "description": "egasi/nomi yoki nomi"},
        "title": {"type": "string", "description": "Sarlavha"},
        "body": {"type": "string", "description": "Tavsif (markdown)"},
    },
    dangerous=True,
)
def github_create_issue(repo: str, title: str, body: str) -> str:
    with _client() as c:
        r = c.post(f"/repos/{_repo(repo)}/issues", json={"title": title, "body": body})
        r.raise_for_status()
        return f"Issue ochildi: {r.json()['html_url']}"


@skill(
    description=(
        "GitHub repozitoriydagi faylni yangilaydi yoki yangi fayl yaratib, to'g'ridan-to'g'ri commit/push qiladi. "
        "Mavjud fayl uchun to'liq yangi mazmunni yubor. Asosiy branch'ga push qilinsa, deploy avtomatik ishga tushishi mumkin. "
        "Foydalanuvchi tasdiqlaydi."
    ),
    params={
        "repo": {"type": "string", "description": "egasi/nomi yoki nomi"},
        "path": {"type": "string", "description": "Fayl yo'li, masalan: ali/brain.py"},
        "content": {"type": "string", "description": "Faylning to'liq yangi mazmuni"},
        "message": {"type": "string", "description": "Commit xabari"},
        "branch": {"type": "string", "description": "Branch nomi (bo'sh bo'lsa - standart branch)"},
    },
    required=["repo", "path", "content", "message"],
    dangerous=True,
)
def github_push_file(repo: str, path: str, content: str, message: str, branch: str = "") -> str:
    full = _repo(repo)
    path = path.strip().lstrip("/")
    with _client() as c:
        current = c.get(f"/repos/{full}/contents/{path}", params={"ref": branch} if branch else {})
        body = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode()}
        if branch:
            body["branch"] = branch
        if current.status_code == 200:
            body["sha"] = current.json()["sha"]  # mavjud faylni yangilash uchun sha shart
        elif current.status_code != 404:
            current.raise_for_status()
        r = c.put(f"/repos/{full}/contents/{path}", json=body)
        r.raise_for_status()
        commit = r.json()["commit"]["html_url"]
    return f"Push qilindi: {path} -> {commit}"


@skill(
    description=(
        "GitHub repozitoriyni kompyuterga klonlaydi (PROJECTS_DIRS dagi birinchi papkaga), shundan keyin uni loyiha "
        "vositalari, Claude Code yoki Codex bilan o'zgartirish mumkin."
    ),
    params={"repo": {"type": "string", "description": "egasi/nomi yoki nomi"}},
)
def github_clone(repo: str) -> str:
    name = _repo(repo)
    target = config.projects_dirs[0] / name.split("/")[1]
    if target.exists():
        return f"Allaqachon bor: {target}"
    auth = base64.b64encode(f"x-access-token:{config.github_token}".encode()).decode()
    r = subprocess.run(
        ["git", "-c", f"http.extraheader=AUTHORIZATION: basic {auth}", "clone", f"https://github.com/{name}.git", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
    )
    return f"Klonlandi: {target}" if r.returncode == 0 else f"Xato: {r.stderr[-1500:]}"
