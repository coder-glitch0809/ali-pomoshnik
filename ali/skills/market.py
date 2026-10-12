"""Bozor ma'lumotlari: kriptovalyuta narxlari va texnik ko'rsatkichlar (Binance ochiq API, kalit kerak emas)."""
import httpx

from . import skill

BINANCE = "https://api.binance.com/api/v3"
INTERVALS = ["15m", "1h", "4h", "1d", "1w"]


def _sma(values: list[float], n: int) -> float | None:
    return sum(values[-n:]) / n if len(values) >= n else None


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain, avg_loss = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):  # Wilder silliqlash
        avg_gain = (avg_gain * (n - 1) + g) / n
        avg_loss = (avg_loss * (n - 1) + l) / n
    return 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)


def _atr(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
           for i in range(1, len(closes))]
    return sum(trs[-n:]) / n


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f}" if abs(x) >= 1 else f"{x:.6g}"


@skill(
    description=(
        "Kriptovalyuta bozori (Binance): joriy narx, 24 soatlik o'zgarish va hajm, shuningdek tanlangan interval bo'yicha "
        "texnik ko'rsatkichlar - SMA20/50/200, RSI14, ATR14, so'nggi 50 sham ichidagi eng yuqori/past narx va oxirgi shamlar. "
        "Aksiya, forex va oltin uchun web_search ishlat."
    ),
    params={
        "symbol": {"type": "string", "description": "Savdo juftligi, masalan BTCUSDT, ETHUSDT, SOLUSDT"},
        "interval": {"type": "string", "enum": INTERVALS, "description": "Sham oralig'i (standart 4h)"},
    },
    required=["symbol"],
)
def market_data(symbol: str, interval: str = "4h") -> str:
    symbol = symbol.upper().replace("/", "").replace("-", "").strip()
    if interval not in INTERVALS:
        return f"Interval quyidagilardan biri bo'lishi kerak: {', '.join(INTERVALS)}"
    with httpx.Client(timeout=15) as http:
        ticker = http.get(f"{BINANCE}/ticker/24hr", params={"symbol": symbol})
        if ticker.status_code == 400:
            return f"{symbol} juftligi Binance'da topilmadi. To'g'ri yozilishi: BTCUSDT, ETHUSDT kabi."
        ticker.raise_for_status()
        klines = http.get(f"{BINANCE}/klines", params={"symbol": symbol, "interval": interval, "limit": 250})
        klines.raise_for_status()
    t = ticker.json()
    rows = klines.json()
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    price = float(t["lastPrice"])
    rsi = _rsi(closes)
    last = [f"  O {_fmt(float(r[1]))}  H {_fmt(float(r[2]))}  L {_fmt(float(r[3]))}  C {_fmt(float(r[4]))}  V {float(r[5]):,.0f}"
            for r in rows[-5:]]
    return "\n".join([
        f"{symbol} - narx: {_fmt(price)}",
        f"24 soat: {float(t['priceChangePercent']):+.2f}%  | yuqori {_fmt(float(t['highPrice']))}  past {_fmt(float(t['lowPrice']))}"
        f"  | hajm {float(t['quoteVolume']):,.0f} USDT",
        f"Interval {interval} (oxirgi {len(rows)} sham):",
        f"  SMA20 {_fmt(_sma(closes, 20))}  SMA50 {_fmt(_sma(closes, 50))}  SMA200 {_fmt(_sma(closes, 200))}",
        f"  RSI14 {rsi:.1f}" if rsi is not None else "  RSI14 -",
        f"  ATR14 {_fmt(_atr(highs, lows, closes))}",
        f"  So'nggi 50 sham: max {_fmt(max(highs[-50:]))}  min {_fmt(min(lows[-50:]))}",
        "Oxirgi 5 sham (eskidan yangiga):",
        *last,
    ])
