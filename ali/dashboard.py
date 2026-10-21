"""Asosiy ekran uchun kundalik ma'lumotlar: ob-havo, kripto, aksiya/fyuchers va yangiliklar.

Hammasi bepul, kalitsiz manbalardan: Open-Meteo, Binance, Yahoo Finance (chart), RSS lentalar.
Natija 10 daqiqa keshlanadi - sahifa tez ochiladi va manbalarga ortiqcha so'rov ketmaydi.
"""
import concurrent.futures as cf
import html
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from .hub import hub

log = logging.getLogger("ali.dashboard")

TTL = 600
UA = {"User-Agent": "Mozilla/5.0 (Ali dashboard)"}
TASHKENT = {"name": "Toshkent", "lat": 41.31, "lon": 69.28}
CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "TONUSDT"]
MARKETS = [  # (Yahoo belgisi, ko'rinadigan nom, turi)
    ("^GSPC", "S&P 500", "Indeks"), ("^IXIC", "Nasdaq", "Indeks"), ("^DJI", "Dow Jones", "Indeks"),
    ("ES=F", "S&P fyuchers", "Fyuchers"), ("NQ=F", "Nasdaq fyuchers", "Fyuchers"),
    ("GC=F", "Oltin", "Fyuchers"), ("CL=F", "Neft (WTI)", "Fyuchers"),
    ("AAPL", "Apple", "Aksiya"), ("NVDA", "Nvidia", "Aksiya"), ("TSLA", "Tesla", "Aksiya"),
    ("UZS=X", "USD/UZS", "Valyuta"),
]
NEWS = {  # bo'lim -> RSS manbalar
    "uzbekiston": [("Kun.uz", "https://kun.uz/news/rss"), ("Gazeta.uz", "https://www.gazeta.uz/oz/rss/"),
                   ("Daryo", "https://daryo.uz/feed")],
    "dunyo": [("BBC O'zbek", "https://feeds.bbci.co.uk/uzbek/rss.xml")],
    "kripto": [("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"), ("Cointelegraph", "https://cointelegraph.com/rss")],
}
WEATHER_CODES = {0: ("Ochiq osmon", "☀️"), 1: ("Asosan ochiq", "🌤"), 2: ("Qisman bulutli", "⛅"), 3: ("Bulutli", "☁️"),
                 45: ("Tuman", "🌫"), 48: ("Tuman", "🌫"), 51: ("Mayda yomg'ir", "🌦"), 53: ("Yomg'ir", "🌦"),
                 55: ("Kuchli shivalama", "🌧"), 61: ("Yomg'ir", "🌧"), 63: ("Yomg'ir", "🌧"), 65: ("Kuchli yomg'ir", "🌧"),
                 71: ("Qor", "🌨"), 73: ("Qor", "🌨"), 75: ("Kuchli qor", "❄️"), 80: ("Jala", "🌦"), 81: ("Jala", "🌧"),
                 82: ("Kuchli jala", "⛈"), 95: ("Momaqaldiroq", "⛈"), 96: ("Do'l bilan momaqaldiroq", "⛈"), 99: ("Do'l", "⛈")}

_cache: dict = {}
_lock = threading.Lock()


def _weather(c: httpx.Client) -> dict:
    loc = hub.last_location or {}
    place = ({"name": "Joylashuvingiz", "lat": loc["lat"], "lon": loc["lon"]} if loc.get("lat") is not None else TASHKENT)
    d = c.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": place["lat"], "longitude": place["lon"], "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}).json()
    cur, day = d["current"], d["daily"]
    text, icon = WEATHER_CODES.get(cur["weather_code"], ("", "🌡"))
    return {"place": place["name"], "temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
            "text": text, "icon": icon, "wind": cur["wind_speed_10m"], "humidity": cur["relative_humidity_2m"],
            "days": [{"date": day["time"][i], "max": round(day["temperature_2m_max"][i]),
                      "min": round(day["temperature_2m_min"][i]), "rain": day["precipitation_probability_max"][i],
                      "icon": WEATHER_CODES.get(day["weather_code"][i], ("", "🌡"))[1]} for i in range(len(day["time"]))]}


def _crypto(c: httpx.Client) -> list[dict]:
    rows = c.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbols": str(CRYPTO).replace("'", '"').replace(" ", "")}).json()
    by = {r["symbol"]: r for r in rows}
    return [{"symbol": s.removesuffix("USDT"), "price": float(by[s]["lastPrice"]), "change": float(by[s]["priceChangePercent"])}
            for s in CRYPTO if s in by]


def _market_one(c: httpx.Client, symbol: str, name: str, kind: str) -> dict | None:
    meta = c.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}", params={"range": "1d", "interval": "1d"},
                 headers=UA).json()["chart"]["result"][0]["meta"]
    price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return None
    return {"symbol": symbol, "name": name, "kind": kind, "price": price,
            "change": round((price - prev) / prev * 100, 2) if prev else 0.0}


def _feed(c: httpx.Client, source: str, url: str, limit: int = 6) -> list[dict]:
    root = ET.fromstring(c.get(url, headers=UA, follow_redirects=True).content)
    items = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        if not title:
            continue
        ts = 0.0
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate") or "").timestamp()
        except (TypeError, ValueError):
            pass
        items.append({"title": re.sub(r"\s+", " ", title)[:200], "link": (it.findtext("link") or "").strip(),
                      "source": source, "ts": ts})
        if len(items) >= limit:
            break
    return items


def _safe(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception as e:
        log.warning("Dashboard manbasi ishlamadi (%s): %s", getattr(fn, "__name__", fn), e)
        return default


def build() -> dict:
    with httpx.Client(timeout=12) as c, cf.ThreadPoolExecutor(max_workers=12) as pool:
        weather = pool.submit(_safe, _weather, c)
        crypto = pool.submit(_safe, _crypto, c, default=[])
        markets = [pool.submit(_safe, _market_one, c, *m) for m in MARKETS]
        feeds = {sec: [pool.submit(_safe, _feed, c, name, url, default=[]) for name, url in src] for sec, src in NEWS.items()}
        news = {}
        for sec, futures in feeds.items():
            items = [i for f in futures for i in f.result()]
            news[sec] = sorted(items, key=lambda i: i["ts"], reverse=True)[:10]
        return {"updated": time.time(), "weather": weather.result(), "crypto": crypto.result(),
                "markets": [m for f in markets if (m := f.result())], "news": news}


def get(force: bool = False) -> dict:
    with _lock:
        if not force and _cache.get("data") and time.time() - _cache["at"] < TTL:
            return _cache["data"]
    data = build()
    with _lock:
        _cache.update(data=data, at=time.time())
    return data
