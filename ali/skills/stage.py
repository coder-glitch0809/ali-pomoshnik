"""Professional sahna: mavzuga mos fon (ko'cha, tungi shahar, tahlil paneli), animatsiyali diagramma paneli, LED stol, yugurma satr.

Diagrammalarda SON yo'q: to'qima statistika ko'rsatilmaydi - ular g'oyani tasvirlaydi, yozuvlari sahna matnidan.
Faqat CSS @keyframes - kadrma-kadr render uchun aniq.
"""
import html as html_lib
import re

from . import motion_bg

KINDS = "bars_up, bars_down, line, funnel, donut, compare, steps"
LABELS = {"funnel": ["Ko'rdi", "Qiziqdi", "Yozdi"], "compare": ["Oldin", "Keyin"], "steps": ["Muammo", "Yechim", "Natija"],
          "bars_up": ["Boshi", "O'rtasi", "Natija"], "bars_down": ["Boshi", "O'rtasi", "Oxiri"], "line": ["Boshi", "Natija"],
          "donut": ["Asosiy", "Qolgani"]}
BY_ICON = {"funnel": "funnel", "chart_down": "bars_down", "chart_up": "bars_up", "warning": "compare", "target": "donut",
           "eye": "compare", "clock": "line", "calendar": "steps", "percent": "donut", "money": "bars_up", "idea": "steps",
           "billboard": "compare", "shop": "compare", "star": "line", "users": "funnel", "phone": "line", "heart": "line",
           "megaphone": "funnel", "chat": "steps", "check": "steps", "rocket": "line", "cursor": "funnel"}
TITLES = {"funnel": "Mijoz yo'li", "compare": "Noto'g'ri va to'g'ri", "steps": "Qadamma-qadam", "bars_up": "O'sish",
          "bars_down": "Pasayish", "line": "O'zgarish", "donut": "Asosiy ulush"}
PLACE = {"billboard", "shop", "eye", "idea", "star", "megaphone", "users"}
NIGHT = {"clock", "calendar", "warning", "rocket", "check"}


def backdrop_of(icon: str) -> str:
    return "street" if icon in PLACE else "night" if icon in NIGHT else "dash"


def _esc(x) -> str:
    return html_lib.escape(str(x))


def _windows(x, y, w, h, cols, rows, seed):
    out = []
    for r in range(rows):
        for c in range(cols):
            v = (seed + r * 7 + c * 13) % 5
            if v == 4:
                continue
            fill = "#ffcf66" if v < 2 else "#3b4e7c"
            d = f"animation:twk {2 + (r + c) % 4}s ease-in-out {(r * c) % 3 * .4:.1f}s infinite both" if v == 0 else ""
            out.append(f'<rect x="{x + 18 + c * (w - 24) / cols:.0f}" y="{y + 22 + r * (h - 30) / rows:.0f}" '
                       f'width="{(w - 24) / cols * .6:.0f}" height="{(h - 30) / rows * .55:.0f}" fill="{fill}" style="{d}"/>')
    return "".join(out)


def _backdrop(kind: str, anim: str) -> str:
    """To'liq ekran fon (1080x1920, personaj orqasida)."""
    if kind == "street":  # do'konlar qatori, peshlavhalar, pilon, ko'cha chiroqlari
        shops = ""
        for k, (x, w, h, sign) in enumerate(((-30, 330, 620, "DO'KON"), (310, 300, 500, "MARKET"), (620, 300, 680, "CAFE"), (930, 240, 540, "SHOP"))):
            y = 1560 - h
            shops += (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#141d3b" stroke="#2c3b6c" stroke-width="3"/>'
                      f'{_windows(x, y + 90, w, h - 300, 4, 3, k)}'
                      f'<rect x="{x + 22}" y="{y + 18}" width="{w - 44}" height="66" rx="8" fill="#0a0f22" stroke="#ffb300" stroke-width="4" '
                      f'style="animation:neon 2.2s ease-in-out {k * .5:.1f}s infinite both"/>'
                      f'<text x="{x + w / 2}" y="{y + 64}" text-anchor="middle" fill="#ffd54f" font-size="38" font-weight="900" font-family="Arial Black,Arial">{sign}</text>'
                      f'<rect x="{x + 30}" y="1350" width="{w - 60}" height="210" fill="#1f2d58"/><rect x="{x + 30}" y="1350" width="{w - 60}" height="210" fill="#ffcf66" opacity=".16"/>')
        body = (f'<g style="animation:drift 14s linear infinite alternate both">{shops}</g>'
                '<rect x="0" y="1560" width="1080" height="360" fill="#0a0e1e"/>'
                '<path d="M60 620V1560M60 620H220" stroke="#3d4d7d" stroke-width="10" fill="none"/>'
                '<circle cx="220" cy="634" r="26" fill="#ffd54f" style="animation:neon 3s ease-in-out infinite both"/>')
    elif kind == "night":  # tungi shahar: oyna chiroqlari yonib-o'chadi
        far = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{1600 - y}" fill="#111936"/>{_windows(x, y, w, 500, 3, 6, x)}'
                      for x, y, w in ((-20, 760, 180), (170, 620, 150), (330, 820, 210), (550, 560, 170), (730, 780, 160), (900, 660, 200)))
        body = ('<circle cx="860" cy="330" r="86" fill="#ffe29a" opacity=".85"/><circle cx="825" cy="310" r="80" fill="#0a1024" opacity=".9"/>'
                f'<g style="animation:drift 16s linear infinite alternate both">{far}</g>')
    else:  # tahlil paneli: suzuvchi grafiklar, kartochkalar
        cards = ""
        for k, (x, y, w, h) in enumerate(((30, 560, 300, 200), (750, 520, 300, 220), (40, 1110, 260, 190), (780, 1090, 270, 210), (360, 430, 340, 160))):
            line = " ".join(f"{x + 24 + j * (w - 48) / 6:.0f},{y + h - 40 - ((j * 37 + k * 23) % 90) * (h - 80) / 90:.0f}" for j in range(7))
            cards += (f'<g style="animation:cardf {5 + k}s ease-in-out {k * .3:.1f}s infinite alternate both">'
                      f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="#16224a" stroke="#3b5aa8" stroke-width="3"/>'
                      f'<polyline points="{line}" fill="none" stroke="#39c6ff" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/></g>')
        body = cards
    return (f'<div class="bd" style="animation:{anim}"><svg viewBox="0 0 1080 1920" width="1080" height="1920">{body}</svg></div>')


def _bars(values, labels, start):
    n = len(values)
    w, gap = 96, (440 - 96 * n) / (n + 1)
    out = ""
    for k, v in enumerate(values):
        x = gap + k * (w + gap)
        h = v * 230
        out += (f'<rect x="{x:.0f}" y="{270 - h:.0f}" width="{w}" height="{h:.0f}" rx="10" fill="url(#gb)" style="transform-box:fill-box;'
                f'transform-origin:50% 100%;animation:grow .8s cubic-bezier(.2,.9,.2,1.2) {start + .35 + k * .2:.2f}s both"/>'
                f'<text x="{x + w / 2:.0f}" y="306" class="lb">{_esc(labels[k % len(labels)])}</text>')
    return out + '<path d="M16 272H424" stroke="#6d84c4" stroke-width="3"/>'


def _diagram(kind: str, labels: list[str], start: float, negative: bool = False) -> str:
    labels = [str(x)[:14] for x in labels][:4] or LABELS.get(kind, ["-"])
    labels = (labels + LABELS.get(kind, labels))[:max(len(labels), 2)]
    if kind in ("bars_up", "bars_down"):
        vals = [.35, .62, .95] if kind == "bars_up" else [.95, .6, .28]
        return _bars(vals, labels, start)
    if kind == "line":
        return ('<path d="M20 272H424M20 272V40" stroke="#6d84c4" stroke-width="3"/>'
                f'<path pathLength="1" d="M26 250C100 240 130 190 190 180S280 130 320 100S380 60 416 46" fill="none" stroke="#ffb300" '
                f'stroke-width="9" stroke-linecap="round" style="stroke-dasharray:1;stroke-dashoffset:1;animation:dr 1.5s ease-out {start + .3:.2f}s both"/>'
                f'<circle cx="416" cy="46" r="14" fill="#fff" style="transform-box:fill-box;transform-origin:50% 50%;animation:popin .4s {start + 1.6:.2f}s both"/>'
                f'<text x="60" y="306" class="lb">{_esc(labels[0])}</text><text x="370" y="306" class="lb">{_esc(labels[-1])}</text>')
    if kind == "funnel":
        out = ""
        n = min(len(labels), 3)
        for k in range(n):
            t0, t1 = 210 - k * 60, 210 - (k + 1) * 60
            y0, h = 26 + k * 92, 84
            out += (f'<path d="M{220 - t0} {y0}H{220 + t0}L{220 + t1} {y0 + h}H{220 - t1}Z" fill="url(#gb)" opacity="{1 - k * .12:.2f}" '
                    f'style="animation:slidein .6s ease-out {start + .3 + k * .28:.2f}s both"/>'
                    f'<text x="220" y="{y0 + 54}" class="lb" style="fill:#07102a;font-size:30px;animation:slidein .6s ease-out {start + .3 + k * .28:.2f}s both">{_esc(labels[k])}</text>')
        return out
    if kind == "donut":
        return ('<circle cx="220" cy="140" r="104" fill="none" stroke="#2a3d78" stroke-width="44"/>'
                f'<circle pathLength="1" cx="220" cy="140" r="104" fill="none" stroke="#ffb300" stroke-width="44" transform="rotate(-90 220 140)" '
                f'style="stroke-dasharray:.68 1;stroke-dashoffset:.68;animation:dr 1.3s ease-out {start + .3:.2f}s both"/>'
                f'<text x="110" y="296" class="lb" style="fill:#ffb300">{_esc(labels[0])}</text><text x="330" y="296" class="lb">{_esc(labels[-1])}</text>')
    if kind == "compare":
        a, b = labels[0], labels[-1]
        return (f'<g style="animation:slidein .6s ease-out {start + .3:.2f}s both"><rect x="14" y="30" width="196" height="220" rx="16" fill="#3a1721" stroke="#ff5a5a" stroke-width="4"/>'
                f'<path d="M72 100L150 180M150 100L72 180" stroke="#ff5a5a" stroke-width="14" stroke-linecap="round"/></g>'
                f'<g style="animation:slidein .6s ease-out {start + .7:.2f}s both"><rect x="230" y="30" width="196" height="220" rx="16" fill="#123524" stroke="#3ddc84" stroke-width="4"/>'
                f'<path d="M280 142L314 178L378 102" fill="none" stroke="#3ddc84" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/></g>'
                f'<text x="112" y="296" class="lb">{_esc(a)}</text><text x="328" y="296" class="lb">{_esc(b)}</text>')
    out = '<path d="M64 150H376" stroke="#3b5aa8" stroke-width="8"/>'  # steps
    n = min(len(labels), 3)
    for k in range(n):
        x = 64 + k * 312 / max(1, n - 1)
        out += (f'<g style="transform-box:fill-box;transform-origin:50% 50%;animation:popin .5s {start + .3 + k * .35:.2f}s both">'
                f'<circle cx="{x:.0f}" cy="150" r="46" fill="url(#gb)"/><text x="{x:.0f}" y="168" class="lb" style="fill:#07102a;font-size:50px">{k + 1}</text></g>'
                f'<text x="{x:.0f}" y="244" class="lb" style="font-size:26px;animation:slidein .5s {start + .5 + k * .35:.2f}s both">{_esc(labels[k])}</text>')
    return out


CSS = """
.bd{position:absolute;left:0;top:0;width:1080px;height:1920px;opacity:0}
.bd svg{filter:saturate(1.05)}
.shade{position:absolute;left:0;top:0;width:1080px;height:1920px;background:linear-gradient(#050814f2 0,#05081499 30%,#05081433 55%,#05081488 80%)}
@keyframes bdin{0%{opacity:0;transform:scale(1.12)}12%{opacity:1}88%{opacity:1}100%{opacity:0;transform:scale(1)}}
@keyframes bdlast{0%{opacity:0;transform:scale(1.1)}15%{opacity:1}100%{opacity:1;transform:scale(1)}}
@keyframes drift{from{transform:translateX(-24px)}to{transform:translateX(24px)}}
@keyframes cardf{from{transform:translateY(-16px)}to{transform:translateY(18px)}}
@keyframes twk{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes neon{0%,100%{opacity:1;filter:drop-shadow(0 0 16px #ffb300)}50%{opacity:.72;filter:none}}
.panel{position:absolute;top:470px;width:500px;height:500px;border-radius:30px;opacity:0;box-sizing:border-box;padding:22px 30px;
background:linear-gradient(160deg,#16244fee,#0b1230f2);border:3px solid #ffb300;box-shadow:0 22px 60px #000b,0 0 40px #ff8f0055;overflow:hidden}
.ptitle{font:900 34px/1.12 'Arial Black',Arial,sans-serif;color:#fff;height:80px;overflow:hidden}
.panel svg{position:absolute;left:30px;top:118px;width:440px;height:330px;overflow:visible}
.lb{font:800 25px Arial,sans-serif;fill:#dfe7ff;text-anchor:middle}
.pshine{position:absolute;top:0;left:-40%;width:30%;height:100%;background:linear-gradient(100deg,transparent,#ffffff22,transparent)}
@keyframes pin{0%{opacity:0;transform:translateY(60px) scale(.9)}9%{opacity:1;transform:none}90%{opacity:1;transform:none}100%{opacity:0;transform:translateY(-30px) scale(.97)}}
@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@keyframes dr{to{stroke-dashoffset:0}}
@keyframes popin{0%{transform:scale(0)}70%{transform:scale(1.15)}100%{transform:scale(1)}}
@keyframes slidein{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
@keyframes shine{0%,60%{left:-40%}100%{left:120%}}
.desk{position:absolute;left:-20px;right:-20px;top:1690px;height:250px;background:linear-gradient(#1c2a58,#080d20 60%);border-top:7px solid #ffb300;
box-shadow:0 -14px 50px #ff8f0066,0 -30px 60px #000a}
.deskname{position:absolute;left:0;right:0;top:16px;text-align:center;font:900 50px 'Arial Black',Arial,sans-serif;letter-spacing:10px;color:#ffd54f;
text-shadow:0 0 22px #ff8f00}
.ticker{position:absolute;left:0;right:0;top:90px;height:58px;background:#ffb300;overflow:hidden}
.tick{position:absolute;white-space:nowrap;top:7px;left:0;font:900 36px Arial,sans-serif;color:#07102a;animation:tk 26s linear infinite both}
@keyframes tk{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.s{top:120px;height:360px}.big{font-size:76px;text-shadow:0 0 18px #ffb300,0 6px 30px #000}
.small{font-size:42px;margin-top:18px;text-shadow:0 4px 18px #000}.brand{top:56px;font-size:34px;z-index:3}.bar{z-index:5}
"""


def layer(scenes: list[dict], step: float, dur: float) -> tuple[str, str, str]:
    """(fon + diagrammalar, stol, css). Toq sahnalarda personaj chapda, diagramma o'ngda (rig bilan bir xil)."""
    back, panels, used = [], [], []
    for k, sc in enumerate(scenes):
        last = k == len(scenes) - 1
        start = k * step
        icon = "chat" if last and "visual" not in sc else motion_bg.pick(sc, used)
        used.append(icon)
        length = dur - start if last else step
        lead = .3 if k else 0  # fon va panel oldingisi tugamasdan kiradi
        back.append(_backdrop(sc.get("backdrop") if sc.get("backdrop") in ("street", "night", "dash") else backdrop_of(icon),
                              f"{'bdlast' if last else 'bdin'} {length + lead:.2f}s {start - lead:.2f}s both"))
        d = sc.get("diagram") if isinstance(sc.get("diagram"), dict) else {}
        kind = d.get("type") if d.get("type") in LABELS else BY_ICON.get(icon, "steps")
        labels = d.get("labels") if isinstance(d.get("labels"), list) else LABELS[kind]
        title = str(d.get("title") or TITLES.get(kind, ""))[:44]
        left = 40 if k % 2 == 0 else 540
        anim = f"pin {length + lead:.2f}s {start - lead:.2f}s both" if not last else f"slidein .6s {start - lead:.2f}s both"
        panels.append(f'<div class="panel" style="left:{left}px;animation:{anim}"><div class="ptitle">{_esc(title)}</div>'
                      f'<svg viewBox="0 0 440 330"><defs><linearGradient id="gb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd54f"/>'
                      f'<stop offset="1" stop-color="#ff8f00"/></linearGradient></defs>{_diagram(kind, labels, start)}</svg>'
                      f'<div class="pshine" style="animation:shine 3.4s ease-in-out {start:.2f}s infinite both"></div></div>')
    words = "   •   ".join(re.sub(r"\s+", " ", s.get("big", "")) for s in scenes) + "   •   "
    desk = (f'<div class="desk"><div class="deskname">PLANET PRINT</div><div class="ticker"><div class="tick">{_esc(words * 6)}</div></div></div>')
    return "".join(back) + '<div class="shade"></div>' + "".join(panels), desk, CSS
