"""Ali Chrome'ni boshqaradi (Playwright): kompyuterdagi Google Chrome, Ali'ning alohida profili (data/chrome_ali).

Kirish (login): kerakli saytlarga shu oynada egasi O'ZI bir marta kiradi - sessiya profilda saqlanadi. Ali parol yozmaydi
(parol maydoniga yozish rad etiladi). Xavfli tugmalar (yuborish, to'lash, joylash, o'chirish, sotib olish...) - egasining
tasdig'i bilan. Topshiriq: «Chrome'da ...» - AI har qadamda sahifani ko'rib, keyingi amalni tanlaydi (ko'pi bilan 12 qadam).
"""
import json
import logging
import queue
import re
import threading

from .config import config

log = logging.getLogger("ali.browser")

PROFILE = config.data_dir / "chrome_ali"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
QUERY = re.compile(r"^\s*(chrome|хром|brauzer|браузер)\S*\s*(da|де|ga|га|orqali|оркали)?\b|"
                   r"(chrome|хром|brauzer|браузер)\S*\s+(da|ga|orqali)\s+", re.I)
RISKY = re.compile(r"send|submit|post|publish|pay|buy|order|checkout|delete|remove|confirm|share|transfer|"
                   r"yubor|jo'?nat|to'?la|sotib|buyurtma|o'?chir|joyla|tasdiq|отправ|оплат|купить|удал|опубл", re.I)

_jobs: "queue.Queue" = queue.Queue()
_thread: threading.Thread | None = None
_state: dict = {}

SNAPSHOT_JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2 && r.bottom > 0 && r.top < innerHeight * 2; };
  const out = []; let i = 0;
  document.querySelectorAll('a,button,input,textarea,select,[role=button],[role=link],[contenteditable=true]').forEach(e => {
    if (!vis(e) || i >= 80) return;
    e.setAttribute('data-ali', i);
    const label = (e.innerText || e.value || e.placeholder || e.getAttribute('aria-label') || e.title || e.name || '').trim().slice(0, 80);
    out.push({i: i++, tag: e.tagName.toLowerCase(), type: e.type || '', label});
  });
  return {url: location.href, title: document.title, text: document.body.innerText.slice(0, 3500), elements: out};
}"""


def _kill_stale() -> None:
    """Faqat Ali profilidagi (chrome_ali) eski Chrome jarayonlari - egasining oddiy Chrome'iga tegilmaydi."""
    import subprocess
    import time
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -match "
                    "'chrome_ali' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                   capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(2)


def _worker() -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = None
        while True:
            fn, box, done = _jobs.get()
            try:
                if ctx is None or not ctx.pages:
                    PROFILE.mkdir(parents=True, exist_ok=True)
                    try:
                        ctx = p.chromium.launch_persistent_context(str(PROFILE), executable_path=CHROME, headless=False,
                                                                   viewport=None, args=["--start-maximized"])
                    except Exception as e:  # oldingi (osilib qolgan) Ali Chrome'i profilni band qilgan - yopib qayta ochamiz
                        if "ProcessSingleton" not in str(e):
                            raise
                        _kill_stale()
                        ctx = p.chromium.launch_persistent_context(str(PROFILE), executable_path=CHROME, headless=False,
                                                                   viewport=None, args=["--start-maximized"])
                    _state["ctx"] = ctx
                page = ctx.pages[-1] if ctx.pages else ctx.new_page()
                box["result"] = fn(page)
            except Exception as e:  # brauzer yopilgan bo'lsa - keyingi safar qayta ochiladi
                box["error"] = e
                if "closed" in str(e).lower():
                    ctx = None
            finally:
                done.set()


def _call(fn, timeout: float = 90):
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_worker, daemon=True, name="chrome")
        _thread.start()
    box, done = {}, threading.Event()
    _jobs.put((fn, box, done))
    if not done.wait(timeout):
        raise RuntimeError("Brauzer javob bermadi")
    if "error" in box:
        raise RuntimeError(str(box["error"])[:300])
    return box.get("result")


def open_url(url: str) -> dict:
    url = url if re.match(r"https?://", url) else "https://" + url
    return _call(lambda page: (page.goto(url, wait_until="domcontentloaded", timeout=45000), page.wait_for_timeout(1500),
                               page.evaluate(SNAPSHOT_JS))[-1])


def snapshot() -> dict:
    return _call(lambda page: page.evaluate(SNAPSHOT_JS))


def click(i: int, label: str = "", confirm=None) -> dict:
    if RISKY.search(label or "") and not (confirm and confirm("browser_click", {"Tugma": label})):
        raise RuntimeError(f"«{label}» bosilmadi - egasi tasdiqlamadi")

    def go(page):
        page.locator(f"[data-ali='{int(i)}']").first.click(timeout=15000)
        page.wait_for_timeout(1500)
        return page.evaluate(SNAPSHOT_JS)
    return _call(go)


def type_text(i: int, text: str, enter: bool = False) -> dict:
    def go(page):
        el = page.locator(f"[data-ali='{int(i)}']").first
        if (el.get_attribute("type") or "").lower() == "password":
            raise RuntimeError("Parol maydoni - parolni egasi o'zi kiritadi")
        el.fill(text, timeout=15000)
        if enter:
            el.press("Enter")
        page.wait_for_timeout(1500)
        return page.evaluate(SNAPSHOT_JS)
    return _call(go)


def download(i: int, folder) -> str:
    """Element bosilganda yuklanadigan faylni papkaga saqlaydi (masalan Pixabay Music trek)."""
    from pathlib import Path

    def go(page):
        with page.expect_download(timeout=60000) as d:
            page.locator(f"[data-ali='{int(i)}']").first.click(timeout=15000)
        dl = d.value
        dest = Path(folder) / (dl.suggested_filename or "track.mp3")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dl.save_as(str(dest))
        return str(dest)
    return _call(go, 120)


def scroll(down: bool = True) -> dict:
    return _call(lambda page: (page.mouse.wheel(0, 900 if down else -900), page.wait_for_timeout(800),
                               page.evaluate(SNAPSHOT_JS))[-1])


STEP = """Sen Ali'ning brauzer agentisan (egasining Chrome'i). Topshiriq: {goal}
Hozirgi sahifa: {url} | {title}
Sahifa matni (qisqartirilgan):
{text}
Bosiladigan elementlar (raqam: turi «yozuv»):
{elements}
Oldingi qadamlar: {history}
Qoidalar: parol yozma (kirish kerak bo'lsa - "done" qilib egasiga «shu saytga o'zingiz kiring» de); to'lov, xarid, xabar yuborish,
joylash va o'chirishni faqat topshiriqda aniq so'ralgan bo'lsa qil. Maqsadga erishsang yoki imkonsiz bo'lsa - "done".
{extra}
FAQAT JSON: {{"action": "open|click|type|scroll|download|done", "url": "...", "i": 0, "text": "...", "enter": true,
"answer": "done bo'lsa - egasiga natija (o'zbekcha, aniq, topilgan ma'lumot bilan)"}}"""


def agent(goal: str, ready: list[str], confirm=None, steps: int = 12, download_to=None) -> str:
    """Topshiriqni Chrome'da bajaradi: har qadamda sahifa ko'riladi, AI keyingi amalni tanlaydi."""
    from .service import _ask_json
    if not ready:
        return "⚠️ Brauzer agenti uchun AI kerak (Claude/ChatGPT/Gemini) - hozir hammasi band."
    snap, history = snapshot(), []
    for _ in range(steps):
        els = "\n".join(f"{e['i']}: {e['tag']}{'/' + e['type'] if e['type'] else ''} «{e['label']}»" for e in snap["elements"])
        try:
            act = _ask_json(STEP.format(goal=goal, url=snap["url"], title=snap["title"], text=snap["text"][:3000],
                                        elements=els[:4000], history="; ".join(history[-8:]) or "-",
                                        extra=("Fayl yuklash kerak bo'lsa - \"download\" (i - yuklab olish tugmasi)."
                                               if download_to else "")), ready, 180)
        except (ValueError, RuntimeError) as e:
            return f"⚠️ AI keyingi qadamni bermadi: {e}"
        kind = act.get("action")
        try:
            if kind == "done":
                return f"🌐 {act.get('answer', 'Bajarildi')}\n\n({snap['url']})"
            if kind == "open":
                snap = open_url(str(act.get("url", "")))
            elif kind == "click":
                label = next((e["label"] for e in snap["elements"] if e["i"] == int(act.get("i", -1))), "")
                snap = click(int(act.get("i", -1)), label, confirm)
            elif kind == "type":
                snap = type_text(int(act.get("i", -1)), str(act.get("text", "")), bool(act.get("enter")))
            elif kind == "scroll":
                snap = scroll(True)
            elif kind == "download" and download_to:
                saved = download(int(act.get("i", -1)), download_to)
                return f"⬇️ Yuklandi: {saved}"
            history.append(f"{kind} {act.get('url') or act.get('i', '')} {str(act.get('text', ''))[:30]}".strip())
        except RuntimeError as e:
            history.append(f"{kind} XATO: {str(e)[:80]}")
            if "tasdiqlamadi" in str(e) or "Parol" in str(e):
                return f"⏸ {e}"
    return f"🌐 12 qadamda tugamadi. Oxirgi sahifa: {snap['title']} ({snap['url']})"


def is_request(text: str) -> bool:
    return bool(QUERY.search(text or ""))
