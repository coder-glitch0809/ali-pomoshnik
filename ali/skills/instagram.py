"""Instagram analitikasi (Instagram Graph API).

Talablar: Instagram Business yoki Creator akkaunt, Facebook sahifaga ulangan,
Meta Developer ilovasidan olingan access token (instagram_basic, instagram_manage_insights,
pages_read_engagement ruxsatlari). Sozlash: README.md -> Instagram.
"""
import json

import httpx

from ..config import config
from . import skill

MEDIA_FIELDS = "id,caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink"
MEDIA_METRICS = "reach,saved,shares,views,total_interactions"


def _get(path: str, **params) -> dict:
    if not config.ig_access_token:
        raise RuntimeError("IG_ACCESS_TOKEN sozlanmagan (.env)")
    r = httpx.get(
        f"https://graph.facebook.com/{config.ig_graph_version}/{path}",
        params={**params, "access_token": config.ig_access_token},
        timeout=30,
    )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def _account_id(account: str) -> str:
    if not config.ig_accounts:
        raise RuntimeError("IG_ACCOUNTS sozlanmagan (.env)")
    if not account:
        return next(iter(config.ig_accounts.values()))
    if account in config.ig_accounts:
        return config.ig_accounts[account]
    raise RuntimeError(f"Akkaunt topilmadi: {account}. Mavjud: {', '.join(config.ig_accounts)}")


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


@skill(description="Ulangan Instagram akkauntlar ro'yxati.")
def instagram_accounts() -> str:
    return ", ".join(config.ig_accounts) or "Instagram akkauntlar ulanmagan."


@skill(
    description=(
        "Instagram akkaunt analitikasi: profil, obunachilar va oxirgi postlar statistikasi "
        "(qamrov, ko'rishlar, layklar, izohlar, saqlashlar, ulashishlar). Natijani chuqur tahlil qil: qaysi format, mavzu, "
        "vaqt va sarlavha yaxshi ishlaydi, nima uchun - va aniq kontent reja va video g'oyalarini (hook, ssenariy) taklif qil."
    ),
    params={
        "account": {"type": "string", "description": "Akkaunt nomi (bo'sh - birinchisi)"},
        "limit": {"type": "integer", "description": "Nechta oxirgi post (standart 12)"},
    },
    required=[],
)
def instagram_analytics(account: str = "", limit: int = 12) -> str:
    uid = _account_id(account)
    profile = _get(uid, fields="username,name,biography,followers_count,follows_count,media_count")
    media = _get(f"{uid}/media", fields=MEDIA_FIELDS, limit=min(limit, 50)).get("data", [])
    insight_error = None
    for post in media:
        try:
            rows = _get(f"{post['id']}/insights", metric=MEDIA_METRICS).get("data", [])
            post["insights"] = {row["name"]: row["values"][0]["value"] for row in rows}
        except Exception as e:
            insight_error = str(e)
    result = {"profile": profile, "posts": media}
    if insight_error:
        result["insights_error"] = insight_error
    return _dump(result)


@skill(
    description="Instagram post izohlarini o'qiydi - auditoriya nimani so'rayotgani, kayfiyati, savollarini tahlil qilish uchun.",
    params={
        "media_id": {"type": "string", "description": "Post ID (instagram_analytics natijasidan)"},
        "limit": {"type": "integer", "description": "Nechta izoh (standart 50)"},
    },
    required=["media_id"],
)
def instagram_comments(media_id: str, limit: int = 50) -> str:
    return _dump(_get(f"{media_id}/comments", fields="text,username,timestamp,like_count", limit=min(limit, 100)).get("data", []))


@skill(
    description=(
        "Boshqa (raqobatchi yoki ilhom manbai) Instagram biznes/creator akkauntini ko'radi: obunachilar va oxirgi postlar statistikasi. "
        "Ular nima uchun muvaffaqiyatli ekanini tahlil qil va foydalanuvchiga moslab g'oyalar ber."
    ),
    params={
        "username": {"type": "string", "description": "Instagram username (@ siz)"},
        "account": {"type": "string", "description": "Qaysi o'z akkauntimiz orqali so'rash (bo'sh - birinchisi)"},
    },
    required=["username"],
)
def instagram_competitor(username: str, account: str = "") -> str:
    uid = _account_id(account)
    username = username.lstrip("@")
    fields = (
        f"business_discovery.username({username})"
        "{username,name,biography,followers_count,media_count,"
        "media.limit(15){caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink}}"
    )
    return _dump(_get(uid, fields=fields).get("business_discovery", {}))
