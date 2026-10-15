"""Ko'p bozorli signal: kripto (Binance), forex, aksiya, ETF, indeks, fyuchers, obligatsiya (Yahoo ochiq chart API)
va MT5 treyding EA'sining signallari (AZT_signals.csv).

Qoidalar treyding EA bilan bir xil: EMA21/55 trend, RSI filtri, cross/pullback/breakout, swing ortidagi SL
(kamida 1.5 ATR, +0.5 ATR bufer), TP 1.5R / 2.25R / 3R, konfluens kamida 2 ball.
Bu qoidali tahlil: kafolat emas, moliyaviy maslahat emas.
"""
from __future__ import annotations

import csv
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

import httpx

from . import skill
from .market import BINANCE, _atr, _fmt, _rsi

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart"
UA = {"User-Agent": "Mozilla/5.0 (Ali signal engine)"}
MARKETS = ["auto", "crypto", "forex", "stock", "etf", "index", "futures", "bond"]
CCY = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "XAU", "XAG"}
BONDS = {"^TNX", "^TYX", "^FVX", "^IRX"}  # AQSh xazina yield'lari (foizda)
# Yahoo: intervalga mos diapazon va yuqori vaqt ramkasi (trend filtri uchun)
YAHOO_RANGE = {"15m": "60d", "1h": "730d", "1d": "5y"}
YAHOO_HTF = {"15m": ("1h", "730d"), "1h": ("1d", "5y"), "1d": ("1wk", "10y")}
BINANCE_HTF = {"15m": "1d", "1h": "1d", "1d": "1w"}
WATCHLIST = {
    "crypto": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"],
    "stock": ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"],
    "etf": ["SPY", "QQQ", "GLD", "TLT", "IWM"],
    "index": ["^GSPC", "^NDX", "^DJI", "^GDAXI", "^N225"],
    "futures": ["ES=F", "NQ=F", "GC=F", "CL=F", "ZN=F"],
    "bond": ["^TNX", "^TYX", "^FVX", "^IRX"],
}


class Bar(NamedTuple):
    t: int
    o: float
    h: float
    l: float
    c: float


# ---- Indikatorlar -----------------------------------------------------------------

def _ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _macd(closes: list[float]) -> tuple[list[float | None], list[float | None]]:
    fast, slow = _ema(closes, 12), _ema(closes, 26)
    line = [f - s if f is not None and s is not None else None for f, s in zip(fast, slow)]
    valid = [v for v in line if v is not None]
    sig_part = _ema(valid, 9)
    signal: list[float | None] = [None] * (len(line) - len(valid)) + sig_part
    return line, signal


def _detect_market(symbol: str) -> str:
    s = symbol.upper().strip()
    if s.endswith(("USDT", "USDC", "BUSD")) and s.isalpha():
        return "crypto"
    if s.endswith("=F"):
        return "futures"
    if s in BONDS:
        return "bond"
    if s.startswith("^"):
        return "index"
    if s.endswith("=X") or (len(s) == 6 and s.isalpha() and s[:3] in CCY and s[3:] in CCY):
        return "forex"
    return "stock"  # aksiya va ETF bir xil manbadan olinadi


def _fetch(symbol: str, market: str, interval: str, htf: bool = False) -> list[Bar]:
    if market == "crypto":
        iv = BINANCE_HTF[interval] if htf else interval
        with httpx.Client(timeout=15) as http:
            r = http.get(f"{BINANCE}/klines", params={"symbol": symbol, "interval": iv, "limit": 400})
            r.raise_for_status()
        return [Bar(int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in r.json()]
    yahoo_symbol = symbol if market != "forex" or symbol.endswith("=X") else symbol.upper() + "=X"
    iv, rng = YAHOO_HTF[interval] if htf else (interval, YAHOO_RANGE[interval])
    with httpx.Client(timeout=20, headers=UA, follow_redirects=True) as http:
        r = http.get(f"{YAHOO}/{quote(yahoo_symbol, safe='=')}", params={"interval": iv, "range": rng})
    if r.status_code == 429:
        raise RuntimeError("Yahoo so'rov limiti (429): bir necha daqiqadan keyin qayta urinib ko'ring")
    r.raise_for_status()
    result = (r.json().get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"{symbol}: ma'lumot topilmadi (yozilishini tekshiring)")
    res = result[0]
    q = res["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(res.get("timestamp") or []):
        row = (q["open"][i], q["high"][i], q["low"][i], q["close"][i])
        if None not in row:
            bars.append(Bar(t, *row))
    return bars


def _trend(bars: list[Bar]) -> str:
    closes = [b.c for b in bars[:-1]]
    e21, e55 = _ema(closes, 21)[-1], _ema(closes, 55)[-1]
    if e21 is None or e55 is None:
        return "n/a"
    c = closes[-1]
    if e21 > e55 and c > e21:
        return "UP"
    if e21 < e55 and c < e21:
        return "DOWN"
    return "MIXED"


@dataclass
class Plan:
    symbol: str
    market: str
    interval: str
    side: int = 0                 # 1 = LONG, -1 = SHORT, 0 = signal yo'q
    reason: str = ""             # signal yo'q bo'lsa sabab
    setup: str = ""
    entry: float = 0.0
    sl: float = 0.0
    tps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    zone: tuple[float, float] = (0.0, 0.0)
    score: int = 0
    factors: list[str] = field(default_factory=list)
    price: float = 0.0
    rsi: float | None = None
    atr: float | None = None


def analyze(symbol: str, market: str, interval: str, bars: list[Bar], htf: list[Bar]) -> Plan:
    plan = Plan(symbol=symbol, market=market, interval=interval)
    closed = bars[:-1]  # oxirgi sham hali shakllanmoqda - signal faqat yopilgan shamdan
    if len(closed) < 60:
        plan.reason = f"Ma'lumot kam ({len(closed)} sham)"
        return plan
    highs = [b.h for b in closed]
    lows = [b.l for b in closed]
    closes = [b.c for b in closed]
    i = len(closed) - 1
    ema21, ema55 = _ema(closes, 21), _ema(closes, 55)
    e21, e55, p21, p55 = ema21[i], ema55[i], ema21[i - 1], ema55[i - 1]
    atr = _atr(highs, lows, closes, 14)
    rsi = _rsi(closes, 14)
    last = closed[i]
    plan.price, plan.rsi, plan.atr = bars[-1].c, rsi, atr
    if None in (e21, e55, p21, p55, atr) or not atr or rsi is None:
        plan.reason = "Ko'rsatkichlar hali tayyor emas"
        return plan

    if e21 > e55 and last.c > e21:
        side = 1
    elif e21 < e55 and last.c < e21:
        side = -1
    else:
        plan.reason = "EMA21/55 trendi va narx bir-biriga mos emas"
        return plan
    if (side == 1 and not 50 < rsi < 70) or (side == -1 and not 30 < rsi < 50):
        plan.reason = f"RSI filtri: RSI={rsi:.1f} (LONG 50-70, SHORT 30-50)"
        return plan

    # Setup: breakout (oxirgi 20 sham ekstremumi) > EMA cross > EMA pullback
    prior = closed[i - 20:i]
    broken = max(b.h for b in prior) if side == 1 else min(b.l for b in prior)
    breakout = last.c > broken if side == 1 else last.c < broken
    cross = p21 <= p55 if side == 1 else p21 >= p55
    pullback = (last.l <= e21 and last.c > last.o) if side == 1 else (last.h >= e21 and last.c < last.o)
    if breakout:
        plan.setup, zone_mid = "Breakout (20 sham ekstremumi)", broken
        zone = (zone_mid - 0.2 * atr, zone_mid + 0.2 * atr)
    elif cross:
        plan.setup, zone_mid = "EMA cross", e21
        zone = (e21 - 0.25 * atr, e21 + 0.25 * atr)
    elif pullback:
        plan.setup, zone_mid = "EMA pullback", e21
        zone = (e21 - 0.25 * atr, e21 + 0.25 * atr)
    else:
        plan.reason = "Kirish sharti yo'q: na breakout, na EMA cross, na EMA pullback"
        return plan

    # SL: oxirgi 10 sham ekstremumi ortida, kamida 1.5 ATR, +0.5 ATR bufer (EA bilan bir xil)
    entry = last.c
    extreme = min(lows[i - 9:i + 1]) if side == 1 else max(highs[i - 9:i + 1])
    distance = max(1.5 * atr, abs(entry - extreme) + 0.5 * atr)
    sl = entry - side * distance
    tps = tuple(entry + side * distance * r for r in (1.5, 2.25, 3.0))

    # Konfluens: har biri +1 (tasdiq) yoki -1 (qarshi)
    score = 0
    macd, sig = _macd(closes)
    m0, m1, s0 = macd[i], macd[i - 1], sig[i]
    if m0 is not None and m1 is not None and s0 is not None:
        vote = 1 if (m0 > s0 and m0 > m1) else -1 if (m0 < s0 and m0 < m1) else 0
        score += vote * side
        plan.factors.append(f"MACD {'bullish' if vote == 1 else 'bearish' if vote == -1 else 'neytral'}")
    if len(closes) >= 200:
        sma200 = sum(closes[-200:]) / 200
        vote = 1 if last.c > sma200 else -1
        score += vote * side
        plan.factors.append(f"Narx SMA200 {'ustida' if vote == 1 else 'ostida'} ({_fmt(sma200)})")
    htf_trend = _trend(htf) if htf else "n/a"
    if htf_trend in ("UP", "DOWN"):
        vote = 1 if htf_trend == "UP" else -1
        score += vote * side
        plan.factors.append(f"Yuqori vaqt ramkasi trendi: {htf_trend}")
    prev = closed[i - 1]
    body = abs(last.c - last.o)
    rng = last.h - last.l
    lower = min(last.o, last.c) - last.l
    upper = last.h - max(last.o, last.c)
    engulf = (prev.c < prev.o and last.c > last.o and last.c >= prev.o and last.o <= prev.c) if side == 1 else \
             (prev.c > prev.o and last.c < last.o and last.c <= prev.o and last.o >= prev.c)
    pin = rng > 0 and ((lower >= 2 * body and lower >= 0.5 * rng) if side == 1 else (upper >= 2 * body and upper >= 0.5 * rng))
    if engulf or pin:
        score += 1
        plan.factors.append("Engulfing" if engulf else "Pin bar")
    # Oxirgi 50 shamdagi qarshi daraja (swing ekstremumi) TP1 yo'lida bo'lsa -1
    tp1 = tps[0]
    for k in range(max(0, i - 48), i - 1):
        if k < 2 or k + 2 > i:
            continue
        pivot = closed[k].h if side == 1 else closed[k].l
        is_high = closed[k].h >= max(b.h for b in closed[k - 2:k + 3])
        is_low = closed[k].l <= min(b.l for b in closed[k - 2:k + 3])
        if (side == 1 and is_high and entry < pivot < tp1) or (side == -1 and is_low and tp1 < pivot < entry):
            score -= 1
            plan.factors.append(f"Qarshi daraja {_fmt(pivot)} TP1 yo'lida")
            break

    plan.score = score
    if score < 2:
        plan.reason = f"Konfluens {score} < 2 (signal kuchsiz)"
        plan.side = 0
        return plan
    plan.side = side
    plan.entry, plan.sl, plan.tps = entry, sl, tps
    plan.zone = (min(zone), max(zone))
    return plan


def _format_plan(p: Plan) -> str:
    head = f"📊 {p.symbol} ({p.market}, {p.interval})"
    if p.side == 0:
        return "\n".join([
            f"{head} — SIGNAL YO'Q",
            f"Sabab: {p.reason}",
            f"Narx: {_fmt(p.price)}" + (f" | RSI {p.rsi:.1f}" if p.rsi is not None else "") +
            (f" | ATR {_fmt(p.atr)}" if p.atr else ""),
            "Ehtiyot: signal bo'lmasa kirmang - kutish ham qaror.",
        ])
    side = "LONG 🟢" if p.side == 1 else "SHORT 🔴"
    confidence = "KUCHLI" if p.score >= 3 else "O'RTACHA"
    risk = abs(p.entry - p.sl)
    unit = "%" if p.market == "bond" else ""
    lines = [
        f"{head} — {side} | Ishonch: {confidence} (ball {p.score})",
        f"Setup: {p.setup}",
        f"🧭 Kirish zonasi: {_fmt(p.zone[0])} – {_fmt(p.zone[1])}{unit}",
        f"▶️ Kirish: {_fmt(p.entry)}{unit} (zona ichida, sham yopilishi bilan)",
        f"🛑 Stop Loss: {_fmt(p.sl)}{unit} (xavf {risk / p.entry * 100:.2f}%)",
        f"🎯 TP1 {_fmt(p.tps[0])} (1.5R, 50% yopiladi)",
        f"🎯 TP2 {_fmt(p.tps[1])} (2.25R, 25% yopiladi)",
        f"🏁 TP3 {_fmt(p.tps[2])} (3R, qolgan 25%)",
        f"💼 1% risk uchun hajm = depozit × 0.01 ÷ {_fmt(risk)} (birlik/lot)",
        "🧩 Tasdiqlar: " + "; ".join(p.factors),
        "⚠️ Qoida asosidagi tahlil: kafolat emas. Narx zonadan ketsa yoki SL urilsa - reja bekor.",
    ]
    return "\n".join(lines)


def _run(symbol: str, market: str, interval: str) -> Plan:
    symbol = symbol.upper().replace("/", "").replace(" ", "").strip()
    mkt = market if market != "auto" else _detect_market(symbol)
    if mkt == "crypto" and not symbol.endswith(("USDT", "USDC", "BUSD")):
        symbol += "USDT"
    if mkt != "crypto" and interval not in YAHOO_RANGE:
        raise ValueError(f"Kripto bo'lmagan bozorlar uchun interval: {', '.join(YAHOO_RANGE)}")
    bars = _fetch(symbol, mkt, interval)
    htf = _fetch(symbol, mkt, interval, htf=True)
    return analyze(symbol, mkt, interval, bars, htf)


@skill(
    description=(
        "Istalgan bozor uchun aniq savdo signali: kripto, forex, aksiya, ETF, indeks, fyuchers yoki obligatsiya. "
        "Kirish zonasi, SL, TP1/TP2/TP3 (1.5R/2.25R/3R), konfluens bali va 1% risk hajmi. Signal bo'lmasa sababini aytadi. "
        "Ma'lumot: kripto - Binance, qolgani - Yahoo Finance (ochiq). Kafolat emas."
    ),
    params={
        "symbol": {"type": "string", "description": "Belgi: BTCUSDT, EURUSD, XAUUSD, AAPL, SPY, ^GSPC, ES=F, ^TNX"},
        "market": {"type": "string", "enum": MARKETS, "description": "Bozor turi (standart auto - belgidan aniqlanadi)"},
        "interval": {"type": "string", "enum": ["15m", "1h", "1d"], "description": "Sham oralig'i (standart 1h)"},
    },
    required=["symbol"],
)
def trade_signal(symbol: str, market: str = "auto", interval: str = "1h") -> str:
    if market not in MARKETS:
        return f"market quyidagilardan biri bo'lishi kerak: {', '.join(MARKETS)}"
    try:
        return _format_plan(_run(symbol, market, interval))
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError) as e:
        return f"{symbol}: ma'lumot olinmadi - {e}"


@skill(
    description=(
        "Kuzatuv ro'yxatidagi bozorlarni skanerlaydi va faqat amaldagi signallarni kuchi bo'yicha saralab beradi. "
        "market: all, crypto, forex, stock, etf, index, futures, bond."
    ),
    params={
        "market": {"type": "string", "enum": ["all"] + [m for m in MARKETS if m != "auto"],
                   "description": "Qaysi bozorlar (standart all)"},
        "interval": {"type": "string", "enum": ["15m", "1h", "1d"], "description": "Sham oralig'i (standart 1h)"},
    },
    required=[],
)
def signal_scan(market: str = "all", interval: str = "1h") -> str:
    groups = list(WATCHLIST) if market == "all" else [market]
    found: list[Plan] = []
    errors: list[str] = []
    checked = 0
    for g in groups:
        for sym in WATCHLIST.get(g, []):
            checked += 1
            try:
                p = _run(sym, g, interval)
            except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError) as e:
                errors.append(f"{sym}: {e}")
                continue
            if p.side:
                found.append(p)
    found.sort(key=lambda p: (-p.score, p.symbol))
    out = [f"Tekshirildi: {checked} ta belgi, interval {interval}. Amaldagi signal: {len(found)} ta."]
    out += [f"- {p.symbol} ({p.market}) {'LONG' if p.side == 1 else 'SHORT'} | ball {p.score} | "
            f"zona {_fmt(p.zone[0])}-{_fmt(p.zone[1])} | SL {_fmt(p.sl)} | TP1 {_fmt(p.tps[0])} "
            f"TP3 {_fmt(p.tps[2])} | {p.setup}" for p in found]
    if not found:
        out.append("Hozir qoidalarga mos signal yo'q - kutish ham savdo qarori.")
    if errors:
        out.append("Xatolar: " + "; ".join(errors[:6]))
    return "\n".join(out)


def _mt5_files() -> list[Path]:
    env = os.environ.get("MT5_FILES_DIR", "").strip()
    if env:
        return [Path(env) / "AZT_signals.csv"]
    base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    return [Path(p) for p in glob.glob(str(base / "*" / "MQL5" / "Files" / "AZT_signals.csv"))]


@skill(
    description=(
        "MT5 treyding EA (AI Zone Trader) chiqargan so'nggi signallarni o'qiydi: vaqt, belgi, yo'nalish, kirish, SL, TP, zona. "
        "EA ishlayotgan kompyuterda AZT_signals.csv faylidan o'qiladi."
    ),
    params={"limit": {"type": "integer", "description": "Nechta so'nggi signal (standart 10)"}},
    required=[],
)
def mt5_signals(limit: int = 10) -> str:
    files = [f for f in _mt5_files() if f.exists()]
    if not files:
        return "AZT_signals.csv topilmadi: EA hali signal chiqarmagan yoki MT5 Files papkasi noma'lum (MT5_FILES_DIR)."
    rows: list[dict] = []
    for f in files:
        with f.open(encoding="utf-8", errors="replace", newline="") as fh:
            rows += list(csv.DictReader(fh))
    rows = rows[-max(1, min(limit, 100)):]
    if not rows:
        return "Fayl bo'sh: hali signal yo'q."
    lines = [f"So'nggi {len(rows)} ta MT5 signali:"]
    for r in reversed(rows):
        lines.append(f"- {r['time']} {r['symbol']} {r['timeframe']} {r['side']} | {r['setup']} | "
                     f"kirish {r['entry']} SL {r['sl']} TP1 {r['tp1']} TP3 {r['tp3']} | "
                     f"zona {r['zone_low']}-{r['zone_high']} | ball {r['score']}")
    return "\n".join(lines)


def _journal_files() -> list[Path]:
    env = os.environ.get("MT5_FILES_DIR", "").strip()
    base = Path(env) if env else Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    pattern = "AZT_Journal_*.csv" if env else "*/MQL5/Files/AZT_Journal_*.csv"
    return [Path(p) for p in glob.glob(str(base / pattern))]


_OUTCOME = {"1": "TP1 ga yetdi", "-1": "SL urildi", "2": "vaqt tugadi/neytral", "0": "kutilmoqda"}


@skill(
    description=(
        "EA signallarining HAQIQIY natijalari: har bir signal nima bo'ldi (TP1 yetdi / SL urildi / vaqt tugadi), R natija, "
        "yutuq foizi, setup va AI kesimida, savdo qilingan va qilinmagan signallar. Telegramga yuborish uchun tayyor matn."
    ),
    params={
        "limit": {"type": "integer", "description": "Oxirgi nechta signal ro'yxati (standart 10)"},
        "symbol": {"type": "string", "description": "Belgi bo'yicha filtr (ixtiyoriy, masalan EURUSD)"},
    },
    required=[],
)
def signal_results(limit: int = 10, symbol: str = "") -> str:
    files = _journal_files()
    if not files:
        return "Journal fayli topilmadi: EA hali signal yozmagan yoki MT5 Files papkasi noma'lum (MT5_FILES_DIR)."
    rows: list[dict] = []
    for f in files:
        if symbol and symbol.upper() not in f.name.upper():
            continue
        with f.open(encoding="utf-8", errors="replace", newline="") as fh:
            rows += list(csv.DictReader(fh, delimiter=";"))
    if not rows:
        return "Natija yo'q."
    resolved = [r for r in rows if r.get("outcome") in ("1", "-1", "2")]
    wins = [r for r in resolved if r["outcome"] == "1"]
    traded = [r for r in rows if r.get("action") in ("AUTO", "APPROVED")]
    traded_done = [r for r in traded if r.get("outcome") in ("1", "-1", "2")]

    def _sum_r(items):
        return sum(float(r.get("resultR") or 0) for r in items)

    lines = [
        f"Jami signal: {len(rows)} | hal bo'lgan: {len(resolved)} | kutilmoqda: {len(rows) - len(resolved)}",
        f"TP1 ga yetdi: {len(wins)} ({(len(wins) / len(resolved) * 100 if resolved else 0):.0f}%) | "
        f"SL urildi: {sum(1 for r in resolved if r['outcome'] == '-1')}",
        f"Hammasi bo'yicha (agar kirilganda) jami R: {_sum_r(resolved):+.2f}",
        f"Haqiqatda savdo qilingan: {len(traded)} ta, hal bo'lgan {len(traded_done)} ta, "
        f"jami R: {_sum_r(traded_done):+.2f}",
    ]
    by_setup: dict[str, list[dict]] = {}
    for r in resolved:
        by_setup.setdefault(r.get("setup", "?"), []).append(r)
    if by_setup:
        lines.append("Setup bo'yicha:")
        for name, items in sorted(by_setup.items(), key=lambda kv: -len(kv[1])):
            w = sum(1 for r in items if r["outcome"] == "1")
            lines.append(f"- {name}: {w}/{len(items)} ({w / len(items) * 100:.0f}%), R {_sum_r(items):+.2f}")
    lines.append(f"So'nggi {min(limit, len(rows))} ta signal:")
    for r in rows[-max(1, min(limit, 100)):][::-1]:
        res = _OUTCOME.get(r.get("outcome", "0"), "?")
        lines.append(f"- {r.get('time', '')} {r.get('side', '')} {r.get('setup', '')} | harakat: {r.get('action', '')} | "
                     f"{res} | R {r.get('resultR', '') or '-'} | MFE {r.get('mfeR', '') or '-'}R MAE {r.get('maeR', '') or '-'}R")
    return "\n".join(lines)
