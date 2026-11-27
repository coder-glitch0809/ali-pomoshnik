"""Creative studio: idea, storyboard, generated illustrations and MP4."""
import json
import copy
import re
import threading
import uuid
from pathlib import Path

from .config import config

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def create(idea: str, style: str, fmt: str, *, review: bool = False) -> str:
    if not idea.strip():
        raise ValueError("Avval video g‘oyasini yozing")
    if fmt not in ("9:16", "16:9", "1:1"):
        fmt = "9:16"
    if style not in ("2D serial", "Anime", "Fantaziya", "Kino-ertak", "3D multfilm", "Ertak kitobi", "Plastilin", "Realistik"):
        style = "2D serial"
    from . import local_ai
    account_ready = local_ai.access() is True and "codex" in local_ai.connected()
    if config.image_source == "chatgpt_account" and not account_ready:
        raise ValueError("Ruxsatlarda ChatGPT akkauntini ulang, tekshiring va mahalliy AI ruxsatini yoqing.")
    use_openai = not account_ready and bool(config.openai_api_key)
    if not account_ready and not use_openai:
        raise ValueError("Serverda OPENAI_API_KEY ni sozlang yoki Ruxsatlarda mahalliy ChatGPT akkauntini ulang.")
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"id": job_id, "status": "queued", "message": "Navbatda…", "story": None, "video": None,
                         "review": review, "format": fmt, "idea": idea[:1200], "progress": 0, "scene_images": []}
    thread = threading.Thread(target=_run, args=(job_id, idea[:1200], style[:40], fmt, use_openai), daemon=True)
    thread.start()
    return job_id


def get(job_id: str) -> dict | None:
    with _lock:
        item = _jobs.get(job_id)
        if item is None and re.fullmatch(r"[0-9a-f]{32}", job_id):
            try:
                item = json.loads((config.data_dir / "creative_videos" / job_id / "job.json").read_text(encoding="utf-8"))
                if item.get("status") not in ("done", "ready", "error"):
                    item.update(status="error", message="Server qayta ishga tushdi. Yangi video yarating.")
                if item.get("telegram_status") == "sending":
                    item["telegram_status"] = "unknown"
                _jobs[job_id] = item
            except (OSError, ValueError):
                return None
        return copy.deepcopy(item) if item is not None else None


def _update(job_id: str, **values) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)
            if re.fullmatch(r"[0-9a-f]{32}", job_id):
                folder = config.data_dir / "creative_videos" / job_id
                folder.mkdir(parents=True, exist_ok=True)
                temp = folder / "job.tmp"
                temp.write_text(json.dumps(_jobs[job_id], ensure_ascii=False), encoding="utf-8")
                temp.replace(folder / "job.json")


def _run(job_id: str, idea: str, style: str, fmt: str, use_openai: bool) -> None:
    import json
    import logging
    from . import account_images, local_ai, outbox, providers, service, story_video

    log = logging.getLogger("ali.creative_video")
    try:
        _update(job_id, status="planning", progress=3, message="Ali g‘oyangizni sahnalarga ajratyapti…")
        prompt = ("Sen ijodiy video ssenariy muallifisan. Foydalanuvchi g‘oyasi uchun 20-40 soniyali, "
                  "o‘zbek lotin yozuvidagi qisqa hikoya tuz. Mavzu yoki brendni o‘zingcha o‘zgartirma. "
                  "Har sahnada speaker (Hikoyachi yoki qahramon ismi), emotion (neutral, happy, excited, sad, angry, whisper, surprised) yoz. "
                  "Dialoglarni kim aytayotganini aniq ajrat, hikoyachi tabiiy va ifodali gapirsin. O‘zbekcha imlo, o‘/g‘ va tinish belgilarini tekshir. "
                  "5-7 sahna bo‘lsin; har sahnada voice - diktor aytadigan bitta sodda gap, big - ekrandagi "
                  "2-5 so‘z, image - inglizcha batafsil vizual tavsif. Barcha sahnalarda bosh qahramonning "
                  "tashqi ko‘rinishini bir xil saqla; bir xil kadrni takrorlama. Birinchi sahna kuchli hook, "
                  "oxirgi sahnada hikoyaga mos qisqa CTA bo‘lsin: tomoshabinni videoni ulashish, izoh qoldirish "
                  "yoki keyingi qismni kutishga taklif qil. CTA ni voice va big matniga tabiiy kirit. "
                  "Bosh qahramonning ismi va ko‘rinishini alohida character "
                  "maydonida yoz. Rasmlarda yozuv yoki logo bo‘lmasin. Uslub: " + style + ".\n"
                  "FAQAT JSON: {\"title\":\"...\",\"hook\":\"...\",\"character\":\"...\",\"scenes\":[{\"voice\":\"...\","
                  "\"speaker\":\"Hikoyachi\",\"emotion\":\"neutral\",\"big\":\"...\",\"image\":\"...\",\"layout\":\"full\"}],\"caption\":\"...\","
                  "\"hashtags\":\"\",\"mood\":\"cinematic\"}\nG‘oya: " + idea[:1200])
        if use_openai:
            story = service._ask_json(prompt, [], 240)
        else:
            reply = local_ai.ask_pro(prompt, timeout=240, only="codex")
            if not reply:
                raise RuntimeError("ChatGPT ssenariy qaytarmadi. Codex akkaunti va obuna limitini tekshiring.")
            raw = reply[1]
            try:
                story = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            except ValueError:
                raise RuntimeError("ChatGPT ssenariyni kutilgan JSON formatida qaytarmadi.") from None
        scenes = [s for s in story.get("scenes", []) if isinstance(s, dict) and str(s.get("voice", "")).strip()]
        if not scenes:
            raise RuntimeError("Ali g‘oyaga mos ssenariy yarata olmadi")
        story["scenes"] = scenes[:6]
        source = "OpenAI API" if use_openai else "ChatGPT akkaunti"
        story["style"] = style
        last_voice = str(story["scenes"][-1].get("voice", "")).casefold()
        cta_words = ("obuna", "ulashing", "ulash", "izoh", "fikr", "davomini", "davomida", "like", "kuzat")
        if not any(word in last_voice for word in cta_words):
            cta = str(story.get("cta") or "Hikoya yoqqan bo‘lsa, do‘stlaringizga ulashing va keyingi qism uchun obuna bo‘ling.")[:180]
            story["scenes"].append({
                "voice": cta,
                "big": "Hikoya yoqdimi? Davomini kuting!",
                "image": "The main character smiles and waves goodbye, warm ending shot, inviting composition",
                "layout": "full",
            })
        story["scenes"] = story["scenes"][:7]
        if not story["scenes"]:
            raise RuntimeError("Ssenariyda sahnalar topilmadi")
        character = str(story.get("character") or story["scenes"][0].get("image", idea))[:500]
        if use_openai:
            story_video.design_plan(story, [])
        style_visual = {
            "2D serial": "2D animated series, clean outlines, expressive characters",
            "3D multfilm": "polished 3D animated family film, soft cinematic lighting",
            "Anime": "Japanese anime illustration, expressive eyes, dynamic composition",
            "Fantaziya": "storybook fantasy illustration, magical atmosphere, rich details",
            "Kino-ertak": "cinematic fairy tale film still, dramatic warm lighting",
            "Ertak kitobi": "hand-painted children's storybook illustration, paper texture",
            "Plastilin": "handmade plasticine claymation, visible clay texture, miniature set",
        }.get(style, style)
        for scene in story["scenes"]:
            scene["image"] = f"{scene.get('image', '')}. Consistent {style_visual} visual style. Same main character design throughout the story. No text."
        portrait_prompt = ("Character design portrait for this story, " + style_visual + " style. Character identity: "
                          + character + ". " + str(story["scenes"][0].get("image", idea))[:500]
                          + ". Full body, simple clean background, expressive friendly face, consistent character reference, no text.")
        folder = config.data_dir / "creative_videos" / job_id
        folder.mkdir(parents=True, exist_ok=True)
        _update(job_id, status="images", progress=12, message="Qahramon va sahna rasmlari ChatGPT’da yaratilmoqda…", story=story)
        width, height = ((1920, 1080) if fmt == "16:9" else (1080, 1080) if fmt == "1:1" else (1080, 1920))
        size = (width, height)

        def generate_image(prompt: str) -> bytes:
            if use_openai:
                return providers._openai_image(prompt, "medium", size)
            return account_images.generate(prompt, size)

        portrait = folder / "qahramon.png"
        portrait.write_bytes(generate_image(portrait_prompt))
        _update(job_id, progress=20, character=f"/api/creative-video/{job_id}/character", message="Qahramon tayyor. Sahnalar chizilmoqda…")
        image_paths = []
        for index, scene in enumerate(story["scenes"]):
            prompt = f"{style} illustration. Main character (keep this exact design in every scene): {character}. Scene: {scene.get('image', '')}. Story idea: {idea}. No text, no watermark."
            path = folder / f"scene-{index + 1}.png"
            path.write_bytes(generate_image(prompt))
            image_paths.append(str(path))
            _update(job_id, scene_images=[f"/api/creative-video/{job_id}/scene/{n + 1}" for n in range(len(image_paths))], progress=20 + round(40 * len(image_paths) / len(story["scenes"])), message=f"Sahna rasmlari yaratilmoqda… {index + 1}/{len(story['scenes'])}")
        _update(job_id, status="ready", progress=60, message="Sahnalar tayyor. Ovozlarni tanlab, videoni yasang.", source=source)
        if not get(job_id).get("review"):
            _render(job_id)
    except Exception as error:
        log.exception("Creative video job failed")
        _update(job_id, status="error", message=str(error)[:500])


def character_path(job_id: str) -> Path | None:
    folder = (config.data_dir / "creative_videos" / job_id).resolve()
    path = folder / "qahramon.png"
    if folder.parent == (config.data_dir / "creative_videos").resolve() and path.is_file() and not path.is_symlink():
        return path
    return None


def scene_path(job_id: str, index: int) -> Path | None:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id) or not 1 <= index <= 10:
        return None
    folder = config.data_dir / "creative_videos" / job_id
    path = folder / f"scene-{index}.png"
    return path if path.is_file() and not path.is_symlink() else None


def start_render(job_id: str, voices: dict) -> None:
    from . import studio_voice
    job = get(job_id)
    if not job or job.get("status") != "ready":
        raise ValueError("Sahnalar hali tayyor emas yoki video allaqachon yig‘ilmoqda")
    allowed = {v["id"] for v in studio_voice.options()}
    if not isinstance(voices, dict) or any(not isinstance(v, str) or v not in allowed for v in voices.values()):
        raise ValueError("Ro‘yxatdagi ovozlardan tanlang")
    speakers = {str(s.get("speaker") or "Hikoyachi") for s in job["story"]["scenes"]}
    selected = {speaker: voices.get(speaker, "aistudio") for speaker in speakers}
    from . import studio_audio
    for index, scene in enumerate(job['story']['scenes']):
        if selected[str(scene.get('speaker') or 'Hikoyachi')] == 'aistudio' and studio_audio.path(job_id, index+1) is None:
            raise ValueError(f'{index+1}-sahna uchun AI Studio WAV faylini yuklang. API kaliti kerak emas.')
    with _lock:
        if _jobs[job_id].get("status") != "ready":
            raise ValueError("Video allaqachon yig‘ilmoqda")
        _jobs[job_id].update(status="rendering", voices=selected)
    _update(job_id, status="rendering", voices=selected, message="Diktor ovozi tayyorlanmoqda…")
    threading.Thread(target=_render, args=(job_id,), daemon=True).start()


def _render(job_id: str) -> None:
    import logging
    from . import outbox
    from .plugins.video_studio import make_content_video
    try:
        job = get(job_id)
        story = job["story"]
        folder = config.data_dir / "creative_videos" / job_id
        scenes = [{"title": s.get("big") or s.get("voice", "")[:65], "text": s.get("big", ""),
                   "narration": s.get("voice", ""), "speaker": s.get("speaker") or "Hikoyachi",
                   "emotion": s.get("emotion") or "neutral", "duration": 4} for s in story["scenes"]]
        def progress(stage, done, total):
            base, span = {"voice": (60, 15), "frames": (75, 20), "mux": (95, 4)}[stage]
            _update(job_id, status="rendering", stage=stage, stage_done=done, stage_total=total,
                    progress=base + round(span * done / max(total, 1)),
                    message={"voice": "Diktor ovozi", "frames": "Kadrlar yig‘ilmoqda", "mux": "Ovoz va video birlashtirilmoqda"}[stage])
        video = outbox.new_path(f"multik_{job_id}", "mp4")
        from . import studio_audio
        uploads = [studio_audio.path(job_id, i+1) if (job.get('voices') or {}).get(s['speaker']) == 'aistudio' else None
                   for i, s in enumerate(scenes)]
        result = make_content_video(topic=job.get("idea", story.get("title", "Video")), scenes=scenes,
                    format=job.get("format", "9:16"), platform="reels", voice=True, ai_images=False,
                    images=[str(folder / f"scene-{i+1}.png") for i in range(len(scenes))],
                    _output_path=video, _progress=progress, _voice_cast=job.get("voices") or {}, _scene_audio=uploads)
        if not video.is_file():
            raise RuntimeError(result or "MP4 fayli yaratilmadi")
        _update(job_id, status="done", stage="done", progress=100, message="Video tayyor", video=video.name, result=result)
    except Exception as error:
        logging.getLogger(__name__).exception("Creative render failed")
        _update(job_id, status="ready" if get(job_id).get("review") else "error", progress=60,
                message="Video yig‘ilmadi: " + str(error)[:450])


async def send_telegram(job_id: str) -> str:
    from .telegram_memory import MemoryBot
    from . import outbox
    job = get(job_id)
    if not job or job.get("status") != "done":
        raise ValueError("Video hali tayyor emas")
    token = config.multik_bot_token or config.telegram_token
    if not token or not config.telegram_owner_id:
        raise ValueError("Telegram bot va egasining chat ID sini sozlang")
    path = outbox.resolve(job.get("video", ""))
    if not path or not path.is_file():
        raise ValueError("Tayyor video fayli topilmadi")
    with _lock:
        state = _jobs[job_id].get("telegram_status")
        if state in ("sending", "sent"):
            return "Telegram’ga yuborilgan" if state == "sent" else "Telegram’ga yuborilmoqda"
        _jobs[job_id]["telegram_status"] = "sending"
    _update(job_id, telegram_status="sending")
    try:
        async with MemoryBot(token, source='Multik' if config.multik_bot_token else 'Ali') as bot:
            with path.open("rb") as stream:
                await bot.send_video(chat_id=config.telegram_owner_id, video=stream,
                    caption=str(job.get("story", {}).get("title", "Ali videosi"))[:900],
                    supports_streaming=True, read_timeout=180, write_timeout=180)
        _update(job_id, telegram_status="sent")
        return "Video Telegram botdagi shaxsiy chattingizga yuborildi"
    except Exception:
        _update(job_id, telegram_status="error")
        raise ValueError("Telegram’ga yuborilmadi. Botni /start bilan ochganingizni tekshiring va qayta urining.") from None
