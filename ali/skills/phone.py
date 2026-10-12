"""Telefon va joylashuv: telefonda havola ochish, xabar yuborish, joylashuv va ob-havo."""
import json

import httpx

from ..hub import hub
from . import skill

UA = {"User-Agent": "Ali-assistant/1.0"}

WEATHER_CODES = {
    0: "ochiq osmon", 1: "asosan ochiq", 2: "qisman bulutli", 3: "bulutli", 45: "tuman", 48: "qirovli tuman",
    51: "mayda yomg'ir", 53: "mayda yomg'ir", 55: "kuchli mayda yomg'ir", 61: "yengil yomg'ir", 63: "yomg'ir",
    65: "kuchli yomg'ir", 71: "yengil qor", 73: "qor", 75: "kuchli qor", 80: "jala", 81: "kuchli jala",
    82: "juda kuchli jala", 95: "momaqaldiroq", 96: "do'l bilan momaqaldiroq", 99: "kuchli do'l",
}


@skill(
    description="Foydalanuvchining telefonida havola ochadi (YouTube, xarita, sayt va h.k.). Telefon ilovasi ochiq bo'lishi kerak.",
    params={
        "url": {"type": "string", "description": "To'liq URL"},
        "title": {"type": "string", "description": "Qisqa sarlavha"},
    },
    required=["url"],
)
def phone_open_url(url: str, title: str = "Havola") -> str:
    n = hub.broadcast({"type": "action", "action": "open_url", "url": url, "title": title}, kind="phone")
    return f"Telefonga yuborildi ({n} qurilma)" if n else "Telefon ulanmagan - telefonda Ali saytini oching."


@skill(
    description="Telefonga bildirishnoma (xabar) yuboradi: ochiq Ali ilovasiga va Telegram botga.",
    params={"text": {"type": "string", "description": "Xabar matni"}},
)
def phone_notify(text: str) -> str:
    n = hub.broadcast({"type": "action", "action": "notify", "text": text}, kind="phone")
    for listener in hub.listeners:
        listener.on_notify(text)
    n += len(hub.listeners)
    return f"Yuborildi ({n} kanal)" if n else "Telefon ham, Telegram ham ulanmagan."


def _reverse_geocode(lat: float, lon: float) -> str:
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "json", "lat": lat, "lon": lon, "accept-language": "uz"},
            headers=UA, timeout=10,
        )
        return r.json().get("display_name", "")
    except Exception:
        return ""


@skill(description="Foydalanuvchining hozirgi joylashuvi (telefon/brauzer GPS orqali): koordinatalar va manzil.")
def get_my_location() -> str:
    loc = hub.last_location
    if not loc:
        return "Joylashuv noma'lum. Ilovada joylashuvga ruxsat berilishi kerak."
    address = _reverse_geocode(loc["lat"], loc["lon"])
    return json.dumps({**loc, "address": address}, ensure_ascii=False)


@skill(
    description="Ob-havo: hozirgi holat va 3 kunlik prognoz. Shahar berilmasa, foydalanuvchi joylashuvi ishlatiladi.",
    params={"city": {"type": "string", "description": "Shahar nomi (ixtiyoriy)"}},
    required=[],
)
def get_weather(city: str = "") -> str:
    if city:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "uz"}, timeout=10,
        ).json()
        if not geo.get("results"):
            return f"Shahar topilmadi: {city}"
        place = geo["results"][0]
        lat, lon, name = place["latitude"], place["longitude"], place["name"]
    elif hub.last_location:
        lat, lon, name = hub.last_location["lat"], hub.last_location["lon"], "joriy joylashuv"
    else:
        return "Shahar ayting yoki joylashuvga ruxsat bering."

    data = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        },
        timeout=10,
    ).json()
    cur, daily = data["current"], data["daily"]
    lines = [
        f"{name}: {cur['temperature_2m']}°C (his qilinishi {cur['apparent_temperature']}°C), "
        f"{WEATHER_CODES.get(cur['weather_code'], '')}, namlik {cur['relative_humidity_2m']}%, "
        f"shamol {cur['wind_speed_10m']} km/soat"
    ]
    for i, day in enumerate(daily["time"]):
        lines.append(
            f"{day}: {daily['temperature_2m_min'][i]}..{daily['temperature_2m_max'][i]}°C, "
            f"{WEATHER_CODES.get(daily['weather_code'][i], '')}, yog'ingarchilik {daily['precipitation_probability_max'][i]}%"
        )
    return "\n".join(lines)
