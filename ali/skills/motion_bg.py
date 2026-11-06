"""Mavzuga mos motion-grafika (personaj orqasida): har sahna o'z belgisini oladi (grafik, voronka, nishon, telefon, pul...),
belgi chiziqma-chiziq «chiziladi», suzadi, orqada katta xira nusxasi aylanadi. Doimiy fon: harakatlanuvchi to'r, uchqunlar,
personaj boshidan tarqaluvchi to'lqinlar (gapirayotgani sezilsin). Faqat CSS @keyframes - kadrma-kadr render uchun aniq."""
import re

S = 'pathLength="1"'
ICONS = {
    "chart_up": f'<path {S} d="M10 90V10M10 90H92"/><rect class="grow" x="20" y="60" width="10" height="30"/>'
                f'<rect class="grow" x="42" y="48" width="10" height="42"/><rect class="grow" x="64" y="30" width="10" height="60"/>'
                f'<path {S} class="hot" d="M14 76L34 58L50 66L70 38L88 20"/><path {S} class="hot" d="M76 20H88V32"/>',
    "chart_down": f'<path {S} d="M10 90V10M10 90H92"/><rect class="grow" x="20" y="30" width="10" height="60"/>'
                  f'<rect class="grow" x="42" y="50" width="10" height="40"/><rect class="grow" x="64" y="72" width="10" height="18"/>'
                  f'<path {S} class="hot" d="M14 22L34 38L50 32L70 60L88 78"/><path {S} class="hot" d="M76 78H88V66"/>',
    "funnel": f'<path {S} d="M8 12H92L60 50V80L40 92V50Z"/><path {S} d="M20 26H80M32 40H68"/>'
              f'<circle class="drop" cx="30" cy="4" r="3"/><circle class="drop d2" cx="50" cy="4" r="3"/>'
              f'<circle class="drop d3" cx="70" cy="4" r="3"/>',
    "target": f'<circle {S} cx="46" cy="54" r="38"/><circle {S} cx="46" cy="54" r="25"/><circle {S} class="hot" cx="46" cy="54" r="11"/>'
              f'<path {S} class="hot" d="M94 6L50 50M94 6L80 8M94 6L92 20"/>',
    "phone": f'<rect {S} x="28" y="6" width="44" height="88" rx="9"/><path {S} d="M44 14H56"/>'
             f'<path {S} class="hot" d="M50 66C38 56 34 46 41 41C45 38 50 41 50 45C50 41 55 38 59 41C66 46 62 56 50 66Z"/>'
             f'<path class="pop" d="M84 30C78 25 76 20 80 18C82 17 84 18 84 20C84 18 86 17 88 18C92 20 90 25 84 30Z"/>'
             f'<path class="pop d2" d="M14 44C8 39 6 34 10 32C12 31 14 32 14 34C14 32 16 31 18 32C22 34 20 39 14 44Z"/>',
    "heart": f'<path {S} class="hot" d="M50 86C20 64 8 48 14 32C20 16 40 14 50 30C60 14 80 16 86 32C92 48 80 64 50 86Z"/>'
             f'<path class="pop" d="M88 20C82 15 80 10 84 8C86 7 88 8 88 10C88 8 90 7 92 8C96 10 94 15 88 20Z"/>',
    "eye": f'<path {S} d="M4 50C26 18 74 18 96 50C74 82 26 82 4 50Z"/><circle {S} class="hot" cx="50" cy="50" r="15"/>'
           f'<circle class="dot" cx="50" cy="50" r="6"/>',
    "clock": f'<circle {S} cx="50" cy="50" r="40"/><path {S} d="M50 14V20M50 80V86M14 50H20M80 50H86"/>'
             f'<path class="spin hot" d="M50 50V22"/><path class="spin slow" d="M50 50H70"/>',
    "money": f'<circle {S} cx="50" cy="50" r="38"/><circle {S} class="hot" cx="50" cy="50" r="28"/>'
             f'<text x="50" y="57" text-anchor="middle" class="t">SO\'M</text>'
             f'<circle class="drop" cx="20" cy="4" r="4"/><circle class="drop d2" cx="82" cy="4" r="4"/>',
    "megaphone": f'<path {S} d="M12 40V60H26L70 84V16L26 40Z"/><path {S} d="M26 60L32 86H42L38 62"/>'
                 f'<path {S} class="hot wave" d="M80 36C86 42 86 58 80 64"/><path {S} class="hot wave d2" d="M88 26C99 40 99 60 88 74"/>',
    "billboard": f'<path {S} d="M6 12H94V60H6Z"/><path {S} d="M42 60V96M58 60V96"/>'
                 f'<path {S} class="hot wave" d="M18 4L22 9M50 0V7M82 4L78 9"/>'
                 f'<text x="50" y="42" text-anchor="middle" class="t">REKLAMA</text>',
    "idea": f'<path {S} class="hot" d="M50 8C30 8 21 27 28 42C32 51 38 55 38 66H62C62 55 68 51 72 42C79 27 70 8 50 8Z"/>'
            f'<path {S} d="M40 74H60M42 82H58M46 90H54"/><path {S} class="wave" d="M8 34H16M84 34H92M18 10L24 16M82 10L76 16"/>',
    "users": f'<circle {S} cx="36" cy="34" r="13"/><circle {S} class="hot" cx="68" cy="38" r="11"/>'
             f'<path {S} d="M12 88C12 62 60 62 60 88"/><path {S} class="hot" d="M56 70C62 60 88 60 90 86"/>',
    "cursor": f'<path {S} class="hot" d="M30 14L30 76L44 62L56 88L66 84L54 58L74 58Z"/>'
              f'<circle class="ring" cx="30" cy="14" r="10"/><circle class="ring d2" cx="30" cy="14" r="10"/>',
    "warning": f'<path {S} class="hot" d="M50 6L95 88H5Z"/><path {S} d="M50 34V62"/><circle class="dot" cx="50" cy="74" r="4"/>',
    "check": f'<circle {S} cx="50" cy="50" r="40"/><path {S} class="hot" d="M28 52L44 68L74 34"/>',
    "rocket": f'<path {S} d="M50 4C67 19 71 44 64 66H36C29 44 33 19 50 4Z"/><circle {S} class="hot" cx="50" cy="34" r="8"/>'
              f'<path {S} d="M36 52L20 72L36 68M64 52L80 72L64 68"/><path class="flick" d="M41 70L50 96L59 70Z"/>',
    "chat": f'<path {S} d="M8 14H92V66H40L22 86V66H8Z"/><circle class="dot blink" cx="32" cy="40" r="5"/>'
            f'<circle class="dot blink d2" cx="50" cy="40" r="5"/><circle class="dot blink d3" cx="68" cy="40" r="5"/>',
    "percent": f'<path {S} class="hot" d="M82 12L18 88"/><circle {S} cx="27" cy="25" r="13"/><circle {S} cx="73" cy="75" r="13"/>',
    "calendar": f'<rect {S} x="10" y="18" width="80" height="72" rx="7"/><path {S} d="M10 36H90M32 8V26M68 8V26"/>'
                f'<path {S} class="hot" d="M34 62L46 74L68 50"/>',
    "shop": f'<path {S} class="hot" d="M8 40L16 12H84L92 40Z"/><path {S} d="M14 40V90H86V40"/><path {S} d="M42 90V62H58V90"/>'
            f'<path {S} class="wave" d="M20 40C20 48 32 48 32 40C32 48 44 48 44 40C44 48 56 48 56 40C56 48 68 48 68 40C68 48 80 48 80 40"/>',
    "star": f'<path {S} class="hot" d="M50 6L62 36L94 38L69 58L78 90L50 72L22 90L31 58L6 38L38 36Z"/>',
}

# kalit so'zlar (lotin + kirill + rus) - AI belgi tanlamasa
WORDS = [
    ("warning", r"xato|хато|ошибк|muammo|муаммо|zaif|заиф|noto.?g.?ri|нотўғри|eskir|эскир|xavf"),
    ("chart_down", r"yo.?qol|йўқол|tushib|тушиб|kamay|камай|pasay|пасай|паден|теря|kam\b"),
    ("funnel", r"voronka|воронка|funnel|lid|лид|konversiya|конверс"),
    ("target", r"target|таргет|auditoriya|аудитор|maqsad|nishon|нишон"),
    ("heart", r"layk|like|vovlech|вовлеч|engagement|yoqtir|ёқтир"),
    ("phone", r"instagram|инстаграм|reels|рилс|telefon|телефон|smm|stories|сторис"),
    ("chat", r"direkt|директ|yozing|ёзинг|javob|жавоб|xabar|хабар|savol|савол|izoh"),
    ("percent", r"foiz|фоиз|%|скидк|процент|chegirma|чегирма"),
    ("money", r"narx|нарх|pul|пул|so.?m\b|сўм|byudjet|бюджет|tejam|тежам|arzon|арзон|daromad|даромад"),
    ("clock", r"vaqt|вақт|soniya|сония|daqiqa|дақиқа|kech|кеч|soat|соат|время|секунд"),
    ("calendar", r"\bkun|кун|hafta|ҳафта|jadval|reja|режа|oy\b"),
    ("billboard", r"pilon|пилон|bilbord|banner|баннер|lightbox|лайтбокс|vivesk|вывеск|peshlavha|пешлавҳа|tashqi|harf|ҳарф"),
    ("eye", r"ko.?rin|кўрин|e.?tibor|эътибор|diqqat|диққат|qamrov|қамров|охват|birinchi soniya|1.?soniya|hook|хук"),
    ("megaphone", r"reklama|реклама|aksiya|акция|e.?lon|эълон|kreativ|креатив"),
    ("idea", r"g.?oya|ғоя|maslahat|маслаҳат|sir\b|сир|yechim|ечим|совет|fikr"),
    ("users", r"mijoz|мижоз|klient|клиент|odam|одам|tadbirkor|тадбиркор|jamoa"),
    ("shop", r"do.?kon|дўкон|vitrina|витрина|savdo|савдо|biznes|бизнес"),
    ("check", r"kafolat|кафолат|ishonch|ишонч|sifat|сифат|tayyor|тайёр|гарант"),
    ("chart_up", r"o.?sish|ўсиш|ko.?pay|кўпай|oshir|ошир|natija|натижа|sotuv|сотув|рост|продаж"),
    ("rocket", r"tez|тез|boost|o.?stir|ўстир|start|старт"),
    ("star", r"eng yaxshi|энг яхши|top|zo.?r|зўр|premium"),
]
FALLBACK = ["idea", "chart_up", "target", "eye", "users", "star"]
KEYS = ", ".join(ICONS)


def pick(scene: dict, used: list[str]) -> str:
    """Sahna uchun belgi: AI tanlagani (visual) -> kalit so'z -> takrorlanmaydigan umumiy."""
    if scene.get("visual") in ICONS:
        return scene["visual"]
    text = f"{scene.get('big', '')} {scene.get('small', '')}".lower()
    for key, rx in WORDS:
        if key not in used[-1:] and re.search(rx, text):
            return key
    return next((k for k in FALLBACK if k not in used), FALLBACK[len(used) % len(FALLBACK)])


CSS = """
.grid{position:absolute;left:-50%;width:200%;top:1180px;height:1100px;transform:perspective(500px) rotateX(62deg);
transform-origin:50% 0;background-image:linear-gradient(rgba(255,179,0,.35) 2px,transparent 2px),
linear-gradient(90deg,rgba(255,179,0,.35) 2px,transparent 2px);background-size:90px 90px;
-webkit-mask-image:linear-gradient(transparent,#000 35%);animation:gridmove 2s linear infinite both}
@keyframes gridmove{from{background-position:0 0}to{background-position:0 90px}}
.pt{position:absolute;width:10px;height:10px;border-radius:50%;background:#ffd54f;box-shadow:0 0 14px #ff9800;
animation:rise linear infinite both}
@keyframes rise{0%{transform:translateY(0) scale(.4);opacity:0}15%{opacity:.9}100%{transform:translateY(-1500px) scale(1);opacity:0}}
.ring0{position:absolute;left:540px;top:1080px;width:520px;height:520px;margin:-260px 0 0 -260px;border-radius:50%;
border:5px solid rgba(255,179,0,.55);animation:ringout 2.4s ease-out infinite both}
@keyframes ringout{0%{transform:scale(.6);opacity:.9}100%{transform:scale(1.9);opacity:0}}
.mg{position:absolute;opacity:0}
.mg svg{width:100%;height:100%;overflow:visible;filter:drop-shadow(0 0 10px #ff9800) drop-shadow(0 0 26px rgba(255,109,0,.6))}
.mg svg *{fill:none;stroke:#ffd54f;stroke-width:3.2;stroke-linecap:round;stroke-linejoin:round}
.mg svg .hot{stroke:#ff8f00}
.mg svg [pathLength]{stroke-dasharray:1;stroke-dashoffset:1}
.mg svg .grow{fill:rgba(255,179,0,.45);stroke:none;transform-box:fill-box;transform-origin:50% 100%}
.mg svg .dot,.mg svg .drop,.mg svg .pop,.mg svg .flick{fill:#ffd54f;stroke:none}
.mg svg .t{fill:#fff;stroke:none;font:900 13px 'Arial Black',Arial,sans-serif}
.mg svg .spin{transform-origin:50px 50px}
.mg svg .ring{stroke:#fff;transform-box:fill-box;transform-origin:50% 50%}
.mg .num{position:absolute;left:-10px;top:-20px;width:96px;height:96px;border-radius:50%;background:#ff8f00;color:#05060c;
font:900 52px/96px 'Arial Black',Arial,sans-serif;text-align:center;box-shadow:0 0 30px #ff6d00}
.mg.mgbig svg{filter:none}.mg.mgbig svg *,.mg.mgbig svg .hot{stroke:rgba(255,213,79,.2);stroke-width:1.4}
.mg.mgbig svg .grow,.mg.mgbig svg .dot,.mg.mgbig svg .drop,.mg.mgbig svg .pop,.mg.mgbig svg .flick{fill:rgba(255,213,79,.1);stroke:none}
.mg.mgbig svg .t{fill:rgba(255,255,255,.12);stroke:none}
@keyframes mgin{0%{opacity:0;transform:scale(.5) rotate(-12deg)}10%{opacity:1;transform:none}85%{opacity:1;transform:none}
100%{opacity:0;transform:scale(1.2)}}
@keyframes mgbig{0%{opacity:0;transform:scale(.8) rotate(-8deg)}12%{opacity:1}85%{opacity:1}100%{opacity:0;transform:scale(1.15) rotate(8deg)}}
@keyframes mglast{0%{opacity:0;transform:scale(.5)}12%,100%{opacity:1;transform:none}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes growup{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes bob{0%,100%{translate:0 0}50%{translate:0 -22px}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fall{0%{transform:translateY(0);opacity:0}20%{opacity:1}100%{transform:translateY(80px);opacity:0}}
@keyframes popup{0%{transform:translateY(0) scale(.3);opacity:0}30%{opacity:1}100%{transform:translateY(-40px) scale(1.2);opacity:0}}
@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
@keyframes ripple{0%{transform:scale(.3);opacity:1}100%{transform:scale(2.6);opacity:0}}
@keyframes flick{0%,100%{transform:scaleY(1)}50%{transform:scaleY(.6)}}
"""


def _icon(key: str, start: float, last: bool) -> str:
    """Belgi SVG'si - ichki animatsiyalar sahna boshidan (start) hisoblanadi."""
    d = f"{start + 0.25:.2f}s"
    body = ICONS[key]
    anim = {
        "[pathLength]": f"draw 1.1s ease-out {d} both",
        ".grow": f"growup .9s cubic-bezier(.2,.8,.2,1) {start + 0.5:.2f}s both",
        ".spin": f"spin 2.5s linear {d} infinite both",
        ".spin.slow": f"spin 9s linear {d} infinite both",
        ".drop": f"fall 1.4s ease-in {d} infinite both",
        ".pop": f"popup 1.6s ease-out {d} infinite both",
        ".ring": f"ripple 1.4s ease-out {d} infinite both",
        ".blink": f"pulse 1s ease-in-out {d} infinite both",
        ".wave": f"draw 1.1s ease-out {d} both, pulse 1.2s ease-in-out {start + 1.4:.2f}s infinite both",
        ".flick": f"flick .25s linear {d} infinite both",
    }
    # har elementga inline animatsiya (bir nechta sahnada bir xil belgi bo'lsa ham vaqtlari alohida)
    out = []
    for m in re.finditer(r"<(\w+)([^>]*)/>", body):
        tag, attrs = m.group(1), m.group(2)
        cls = re.search(r'class="([^"]+)"', attrs)
        classes = cls.group(1).split() if cls else []
        a = None
        for sel, val in anim.items():
            if sel == "[pathLength]" and "pathLength" in attrs and not {"wave"} & set(classes):
                a = val
            elif sel.startswith(".") and set(sel[1:].split(".")) <= set(classes):
                a = val
        if "d2" in classes and a:
            a = re.sub(r"(\d+\.\d+)s (infinite|both)", lambda x: f"{float(x.group(1)) + 0.5:.2f}s {x.group(2)}", a, count=1)
        if "d3" in classes and a:
            a = re.sub(r"(\d+\.\d+)s (infinite|both)", lambda x: f"{float(x.group(1)) + 1.0:.2f}s {x.group(2)}", a, count=1)
        out.append(f'<{tag}{attrs} style="animation:{a}"/>' if a else m.group(0))
    rest = re.sub(r"<(\w+)([^>]*)/>", "", body)  # <text>...</text>
    return f'<svg viewBox="0 0 100 100">{"".join(out)}{rest}</svg>'


def layer(scenes: list[dict], step: float, dur: float) -> tuple[str, str]:
    """(html, css): fon to'ri, uchqunlar, to'lqinlar va har sahna belgisi (yonida) + katta xira nusxasi (orqada)."""
    parts = ['<div class="grid"></div>']
    for k in range(22):  # uchqunlar - joyi va tezligi turlicha (tasodifsiz, har safar bir xil)
        x, y, sp, dl = (k * 211) % 1040 + 20, 1500 + (k * 137) % 400, 5 + (k * 7) % 6, -((k * 1.37) % 8)
        parts.append(f'<div class="pt" style="left:{x}px;top:{y}px;animation-duration:{sp}s;animation-delay:{dl:.2f}s"></div>')
    for k in range(3):
        parts.append(f'<div class="ring0" style="animation-delay:{0.8 * k + 0.9:.2f}s"></div>')
    used: list[str] = []
    for k, sc in enumerate(scenes):
        last = k == len(scenes) - 1
        key = "chat" if last and "visual" not in sc else pick(sc, used)
        used.append(key)
        start = k * step
        big = f"{'mglast' if last else 'mgbig'} {(dur - start) if last else step:.2f}s {start:.2f}s both"
        parts.append(f'<div class="mg mgbig" style="left:40px;top:640px;width:1000px;height:1000px;animation:{big}">'
                     f'{_icon(key, start, last)}</div>')
        left = 30 if k % 2 == 0 else 720
        num = "" if last else f'<div class="num">{k + 1 if k else "!"}</div>'
        side = f"{'mglast' if last else 'mgin'} {(dur - start) if last else step:.2f}s {start:.2f}s both"
        parts.append(f'<div class="mg" style="left:{left}px;top:900px;width:330px;height:330px;animation:{side}">'
                     f'<div style="width:100%;height:100%;animation:bob 2.6s ease-in-out {start:.2f}s infinite both">'
                     f'{_icon(key, start, last)}</div>{num}</div>')
    return "".join(parts), CSS
