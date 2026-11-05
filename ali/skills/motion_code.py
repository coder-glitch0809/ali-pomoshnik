"""Kod orqali motion-grafika video: Kontent-meyker matni -> Dasturchi animatsiya kodi (HTML/CSS) -> Chrome'da kadrma-kadr
render -> musiqa. Kunlik 11:00/16:00 Reels ham shu yo'l bilan yasaladi (ali/daily_video.py)."""
from pathlib import Path

from . import skill


@skill(
    description="ANIMATSIYA VIDEO (motion design, kod orqali): mavzu bo'yicha Kontent-meyker sahnalar matnini tuzadi, Dasturchi "
                "HTML/CSS animatsiya kodini yozadi, Ali uni 1080x1920 30 fps videoga aylantirib musiqa qo'shadi (15 s). "
                "Kamera videosi yo'q bo'lganda reklama/e'lon/aksiya Reels uchun. AI band bo'lsa - o'z shabloni bilan.",
    params={"topic": {"type": "string", "description": "Mavzu (masalan: «pilon aksiyasi -20%», «lightbox afzalliklari»)"}},
    required=["topic"],
)
def code_animation_video(topic: str) -> str:
    from .. import daily_video
    res = daily_video.make("Buyurtma", topic=topic)  # natija outbox'da - javob bilan birga yuboriladi
    data = res["idea"]
    return (f"Animatsiya video tayyor: {Path(res['path']).name} - «{data.get('title', '')}» ({res['sources']}).\n"
            f"Hook: {data.get('hook', '')}\nCaption: {data.get('caption', '')}\n{data.get('hashtags', '')}")
