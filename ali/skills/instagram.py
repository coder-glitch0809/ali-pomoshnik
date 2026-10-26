"""Instagram: analitika, post/Reels/Stories/karusel joylash, izohlar va Direct xabarlarini boshqarish.

Ikki xil token qabul qilinadi (Ruxsatlar -> Ulanishlar -> Instagram):
  - "Instagram API with Instagram Login" tokeni (IGAA... - graph.instagram.com). Ruxsatlar:
    instagram_business_basic, instagram_business_content_publish, instagram_business_manage_comments,
    instagram_business_manage_insights, instagram_business_manage_messages.
  - Facebook Login tokeni (EAA... - graph.facebook.com), Facebook sahifaga ulangan Business/Creator akkaunt.
    Ruxsatlar: instagram_basic, instagram_content_publish, instagram_manage_comments, instagram_manage_insights,
    instagram_manage_messages, pages_show_list, pages_read_engagement.
Joylash, javob yozish, o'chirish va xabar yuborish har doim egasining tasdig'i bilan.
"""
import json
import mimetypes
import secrets
import shutil
import time
from pathlib import Path

import httpx

from ..config import config
from . import skill

MEDIA_FIELDS = "id,caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink"
MEDIA_METRICS = "reach,saved,shares,views,total_interactions"
PUBLIC_MEDIA = config.data_dir / "ig_media"  # vaqtinchalik ochiq fayllar (Instagram rasmni URL orqali oladi)


def is_ig_login(token: str | None = None) -> bool:
    return (token or config.ig_access_token or "").startswith("IG")


def _base(token: str | None = None) -> str:
    host = "graph.instagram.com" if is_ig_login(token) else "graph.facebook.com"
    return f"https://{host}/{config.ig_graph_version}"


def _token() -> str:
    if not config.ig_access_token:
        raise RuntimeError("Instagram ulanmagan: Ruxsatlar -> Ulanishlar -> Instagram")
    return config.ig_access_token


def _check(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Instagram javobi noto'g'ri (HTTP {r.status_code})")
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def _get(path: str, **params) -> dict:
    return _check(httpx.get(f"{_base()}/{path}", params={**params, "access_token": _token()}, timeout=30))


def _post(path: str, **data) -> dict:
    return _check(httpx.post(f"{_base()}/{path}", data={**data, "access_token": _token()}, timeout=60))


def discover(token: str) -> dict[str, str]:
    """Token orqali Instagram akkaunt(lar)ni topadi: {username: id}."""
    base = _base(token)
    with httpx.Client(timeout=20) as c:
        if is_ig_login(token):
            me = _check(c.get(f"{base}/me", params={"fields": "user_id,username", "access_token": token}))
            return {me["username"]: str(me.get("user_id") or me["id"])}
        pages = _check(c.get(f"{base}/me/accounts", params={
            "fields": "name,instagram_business_account{id,username}", "access_token": token})).get("data", [])
    return {p["instagram_business_account"]["username"]: p["instagram_business_account"]["id"]
            for p in pages if p.get("instagram_business_account")}


TOKEN_STATE = config.data_dir / "ig_token.json"


def refresh_if_needed(days: int = 7) -> str:
    """Instagram Login tokeni (60 kunlik) har `days` kunda yangilanadi - muddati tugab qolmasin.
    Facebook Login tokenini app secret'siz uzaytirib bo'lmaydi - bunday holatda egasi yangisini kiritadi."""
    import json as _json
    import os

    if not config.ig_access_token or not is_ig_login():
        return "skip"
    try:
        last = _json.loads(TOKEN_STATE.read_text(encoding="utf-8")).get("refreshed", 0)
    except (OSError, ValueError):
        last = 0
    if time.time() - last < days * 86400:
        return "fresh"
    r = httpx.get("https://graph.instagram.com/refresh_access_token",
                  params={"grant_type": "ig_refresh_token", "access_token": config.ig_access_token}, timeout=30)
    data = _check(r)
    token = data.get("access_token")
    if token:
        from dotenv import set_key
        from ..config import STATE_ROOT
        set_key(str(STATE_ROOT / ".env"), "IG_ACCESS_TOKEN", token)
        config.ig_access_token = token
        os.environ["IG_ACCESS_TOKEN"] = token
        TOKEN_STATE.write_text(_json.dumps({"refreshed": time.time(), "expires_in": data.get("expires_in")}), encoding="utf-8")
        return "refreshed"
    return "no-token"


def _account_id(account: str) -> str:
    if not config.ig_accounts:
        raise RuntimeError("Instagram akkaunt topilmadi - Ruxsatlar bo'limida Instagram'ni qayta ulang")
    if not account:
        return next(iter(config.ig_accounts.values()))
    name = account.lstrip("@")
    if name in config.ig_accounts:
        return config.ig_accounts[name]
    raise RuntimeError(f"Akkaunt topilmadi: {account}. Mavjud: {', '.join(config.ig_accounts)}")


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


ACCOUNT = {"type": "string", "description": "Akkaunt username (bo'sh - birinchisi)"}


@skill(description="Ulangan Instagram akkauntlar ro'yxati va token turi.")
def instagram_accounts() -> str:
    if not config.ig_accounts:
        return "Instagram akkauntlar ulanmagan."
    kind = "Instagram Login" if is_ig_login() else "Facebook Login"
    return f"{', '.join('@' + a for a in config.ig_accounts)} ({kind})"


@skill(
    description=(
        "Instagram akkaunt analitikasi: profil, obunachilar va oxirgi postlar statistikasi "
        "(qamrov, ko'rishlar, layklar, izohlar, saqlashlar, ulashishlar). Natijani chuqur tahlil qil: qaysi format, mavzu, "
        "vaqt va sarlavha yaxshi ishlaydi, nima uchun - va aniq kontent reja va video g'oyalarini (hook, ssenariy) taklif qil."
    ),
    params={"account": ACCOUNT, "limit": {"type": "integer", "description": "Nechta oxirgi post (standart 12)"}},
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
    description=(
        "Instagram akkauntning umumiy statistikasi tanlangan davr uchun: qamrov, ko'rishlar, faol auditoriya, "
        "o'zaro ta'sirlar, profilga tashriflar, havola bosilishlari, yangi obunachilar."
    ),
    params={"account": ACCOUNT, "days": {"type": "integer", "description": "Oxirgi necha kun (1-30, standart 7)"}},
    required=[],
)
def instagram_insights(account: str = "", days: int = 7) -> str:
    uid = _account_id(account)
    until = int(time.time())
    since = until - max(1, min(days, 30)) * 86400
    out, errors = {}, []
    for metric in ("reach", "views", "accounts_engaged", "total_interactions", "profile_views", "website_clicks",
                   "follows_and_unfollows"):
        try:
            rows = _get(f"{uid}/insights", metric=metric, period="day", metric_type="total_value",
                        since=since, until=until).get("data", [])
            for row in rows:
                out[row["name"]] = row.get("total_value", row.get("values"))
        except RuntimeError as e:
            errors.append(f"{metric}: {e}")
    return _dump({"days": days, "metrics": out, **({"errors": errors} if errors else {})})


@skill(
    description="Instagram post izohlarini o'qiydi (ID lari bilan) - auditoriya nimani so'rayotganini tahlil qilish va javob berish uchun.",
    params={
        "media_id": {"type": "string", "description": "Post ID (instagram_analytics natijasidan)"},
        "limit": {"type": "integer", "description": "Nechta izoh (standart 50)"},
    },
    required=["media_id"],
)
def instagram_comments(media_id: str, limit: int = 50) -> str:
    return _dump(_get(f"{media_id}/comments", fields="id,text,username,timestamp,like_count,hidden",
                      limit=min(limit, 100)).get("data", []))


@skill(
    description=(
        "Boshqa (raqobatchi yoki ilhom manbai) Instagram biznes/creator akkauntini ko'radi: obunachilar va oxirgi postlar. "
        "Faqat Facebook Login tokeni bilan ishlaydi."
    ),
    params={"username": {"type": "string", "description": "Instagram username (@ siz)"}, "account": ACCOUNT},
    required=["username"],
)
def instagram_competitor(username: str, account: str = "") -> str:
    if is_ig_login():
        return "Raqobatchi tahlili faqat Facebook Login tokeni bilan ishlaydi (Instagram API cheklovi). web_search'dan foydalan."
    uid = _account_id(account)
    username = username.lstrip("@")
    fields = (
        f"business_discovery.username({username})"
        "{username,name,biography,followers_count,media_count,"
        "media.limit(15){caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink}}"
    )
    return _dump(_get(uid, fields=fields).get("business_discovery", {}))


# --- joylash ---
def _public_url(src: str) -> str:
    """Rasm uchun ochiq URL: http(s) havola o'zi, kompyuterdagi fayl - vaqtincha PUBLIC_URL orqali."""
    if src.startswith(("http://", "https://")):
        return src
    path = Path(src)
    if not path.is_file():
        raise RuntimeError(f"Fayl topilmadi: {src}")
    if not config.public_url.startswith("https://"):
        raise RuntimeError("Kompyuterdagi rasmni joylash uchun Ali internetdan ochiq bo'lishi kerak (PUBLIC_URL, "
                           "masalan tunnel.bat havolasi) yoki rasmning https havolasini bering.")
    PUBLIC_MEDIA.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(16) + path.suffix.lower()
    shutil.copy2(path, PUBLIC_MEDIA / name)
    return f"{config.public_url}/ig-media/{name}"


def _is_video(src: str) -> bool:
    return (mimetypes.guess_type(src)[0] or "").startswith("video/")


def _container(uid: str, src: str, media_type: str | None, **extra) -> str:
    """Media konteyner yaratadi. Kompyuterdagi video - to'g'ridan-to'g'ri yuklanadi (resumable upload)."""
    video = _is_video(src)
    params = {**extra}
    if media_type:
        params["media_type"] = media_type
    if video and not src.startswith(("http://", "https://")):
        path = Path(src)
        if not path.is_file():
            raise RuntimeError(f"Fayl topilmadi: {src}")
        params["upload_type"] = "resumable"
        cid = _post(f"{uid}/media", **params)["id"]
        data = path.read_bytes()
        r = httpx.post(f"https://rupload.facebook.com/ig-api-upload/{config.ig_graph_version}/{cid}", content=data,
                       headers={"Authorization": f"OAuth {_token()}", "offset": "0", "file_size": str(len(data))},
                       timeout=600)
        _check(r)
        return cid
    params["video_url" if video else "image_url"] = src if video else _public_url(src)
    return _post(f"{uid}/media", **params)["id"]


def _wait(cid: str, minutes: int = 10) -> None:
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        status = _get(cid, fields="status_code,status").get("status_code")
        if status in ("FINISHED", None):
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram mediani qayta ishlay olmadi: {_get(cid, fields='status').get('status')}")
        time.sleep(5)
    raise RuntimeError("Instagram videoni qayta ishlashi juda uzoq davom etdi")


@skill(
    description=(
        "Instagram'ga joylaydi: post (rasm), Reels (video), Stories yoki karusel (2-10 ta rasm/video). media - fayl yo'li "
        "(kompyuterdagi rasm/video, masalan Ali yaratgan rasm) yoki https havola. Joylashdan oldin egasiga caption va "
        "faylni ko'rsatib tasdiq olinadi."
    ),
    params={
        "kind": {"type": "string", "enum": ["post", "reel", "story", "carousel"], "description": "Joylash turi"},
        "media": {"type": "array", "items": {"type": "string"}, "description": "Fayl yo'llari yoki https havolalar"},
        "caption": {"type": "string", "description": "Sarlavha (hashtaglar bilan); Stories uchun e'tiborga olinmaydi"},
        "account": ACCOUNT,
    },
    required=["kind", "media"],
    dangerous=True,
)
def instagram_publish(kind: str, media: list, caption: str = "", account: str = "") -> str:
    uid = _account_id(account)
    media = [str(m) for m in media if str(m).strip()]
    if not media:
        return "media bo'sh"
    extra = {"caption": caption} if caption and kind != "story" else {}
    if kind == "carousel":
        if not 2 <= len(media) <= 10:
            return "Karusel uchun 2-10 ta fayl kerak"
        children = []
        for src in media:
            cid = _container(uid, src, "VIDEO" if _is_video(src) else None, is_carousel_item="true")
            _wait(cid)
            children.append(cid)
        cid = _post(f"{uid}/media", media_type="CAROUSEL", children=",".join(children), **extra)["id"]
    else:
        src = media[0]
        media_type = {"reel": "REELS", "story": "STORIES"}.get(kind)
        if kind == "post" and _is_video(src):
            media_type = "REELS"  # Instagram'da video post - Reels
        cid = _container(uid, src, media_type, **extra)
    _wait(cid)
    published = _post(f"{uid}/media_publish", creation_id=cid)
    link = ""
    try:
        link = _get(published["id"], fields="permalink").get("permalink", "")
    except RuntimeError:
        pass
    for f in PUBLIC_MEDIA.glob("*") if PUBLIC_MEDIA.exists() else []:
        f.unlink(missing_ok=True)  # vaqtinchalik ochiq fayllarni tozalash
    return f"Joylandi ({kind}): {link or published['id']}"


# --- izohlar ---
@skill(
    description="Instagram izohiga javob yozadi (egasi nomidan). Foydalanuvchi tasdiqlaydi.",
    params={"comment_id": {"type": "string", "description": "Izoh ID (instagram_comments)"},
            "message": {"type": "string", "description": "Javob matni"}},
    dangerous=True,
)
def instagram_reply_comment(comment_id: str, message: str) -> str:
    return f"Javob yozildi: {_post(f'{comment_id}/replies', message=message).get('id')}"


@skill(
    description="Instagram izohini yashiradi yoki qayta ko'rsatadi (spam, haqorat). Foydalanuvchi tasdiqlaydi.",
    params={"comment_id": {"type": "string", "description": "Izoh ID"},
            "hide": {"type": "boolean", "description": "true - yashirish, false - ko'rsatish"}},
    dangerous=True,
)
def instagram_hide_comment(comment_id: str, hide: bool) -> str:
    _post(comment_id, hide="true" if hide else "false")
    return "Izoh yashirildi" if hide else "Izoh qayta ko'rsatildi"


@skill(
    description="Instagram izohini butunlay o'chiradi. Qaytarib bo'lmaydi - foydalanuvchi tasdiqlaydi.",
    params={"comment_id": {"type": "string", "description": "Izoh ID"}},
    dangerous=True,
)
def instagram_delete_comment(comment_id: str) -> str:
    _check(httpx.delete(f"{_base()}/{comment_id}", params={"access_token": _token()}, timeout=30))
    return "Izoh o'chirildi"


# --- Direct xabarlari (faqat Instagram Login tokeni) ---
def _need_ig_login():
    if not is_ig_login():
        raise RuntimeError("Direct xabarlari uchun Instagram Login tokeni (IGAA...) kerak - Instagram'ni qayta ulang.")


@skill(
    description="Instagram Direct suhbatlari va oxirgi xabarlar (kim yozgan, nima, qachon) - javob tayyorlash uchun.",
    params={"limit": {"type": "integer", "description": "Nechta suhbat (standart 10)"}},
    required=[],
)
def instagram_messages(limit: int = 10) -> str:
    _need_ig_login()
    data = _get("me/conversations", platform="instagram", limit=min(limit, 25),
                fields="participants,updated_time,messages.limit(5){id,message,from,created_time}")
    return _dump(data.get("data", []))


@skill(
    description=(
        "Instagram Direct'da xabar yuboradi (egasi nomidan). Instagram qoidasi: faqat oxirgi 24 soatda sizga yozgan "
        "odamga. recipient_id - instagram_messages dagi suhbatdoshning id si. Foydalanuvchi tasdiqlaydi."
    ),
    params={"recipient_id": {"type": "string", "description": "Qabul qiluvchi IG ID"},
            "text": {"type": "string", "description": "Xabar matni"}},
    dangerous=True,
)
def instagram_send_message(recipient_id: str, text: str) -> str:
    _need_ig_login()
    r = httpx.post(f"{_base()}/me/messages", json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                   headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
    return f"Yuborildi: {_check(r).get('message_id', 'ok')}"
