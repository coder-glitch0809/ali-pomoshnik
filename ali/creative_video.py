"""Creative studio: idea, storyboard, generated illustrations and MP4."""
import threading
import uuid
from pathlib import Path

from .config import config

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def create(idea: str, style: str, fmt: str) -> str:
    if not idea.strip():
        raise ValueError("Avval video g‘oyasini yozing")
    if fmt not in ("9:16", "16:9", "1:1"):
        fmt = "9:16"
    if style not in ("2D serial", "Anime", "Fantaziya", "Kino-ertak", "3D multfilm", "Ertak kitobi", "Plastilin", "Realistik"):
        style = "2D serial"
    from . import local_ai
    use_openai = bool(config.openai_api_key)
    if not use_openai and (local_ai.access() is not True or "codex" not in local_ai.connected()):
        raise ValueError("Serverda OPENAI_API_KEY ni sozlang yoki Ruxsatlarda mahalliy ChatGPT akkauntini ulang.")
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"id": job_id, "status": "queued", "message": "Navbatda…", "story": None, "video": None}
    thread = threading.Thread(target=_run, args=(job_id, idea[:1200], style[:40], fmt, use_openai), daemon=True)
    thread.start()
    return job_id


def get(job_id: str) -> dict | None:
    with _lock:
        item = _jobs.get(job_id)
        return dict(item) if item else None


def _update(job_id: str, **values) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def _run(job_id: str, idea: str, style: str, fmt: str, use_openai: bool) -> None:
    import logging
    from . import account_images, daily_video, outbox, providers, service, story_video

    log = logging.getLogger("ali.creative_video")
    try:
        _update(job_id, status="planning", message="Ali g‘oyangizni sahnalarga ajratyapti…")
        prompt = ("Sen ijodiy video ssenariy muallifisan. Foydalanuvchi g‘oyasi uchun 20-40 soniyali, "
                  "o‘zbek lotin yozuvidagi qisqa hikoya tuz. Mavzu yoki brendni o‘zingcha o‘zgartirma. "
                  "5-7 sahna bo‘lsin; har sahnada voice - diktor aytadigan bitta sodda gap, big - ekrandagi "
                  "2-5 so‘z, image - inglizcha batafsil vizual tavsif. Barcha sahnalarda bosh qahramonning "
                  "tashqi ko‘rinishini bir xil saqla; bir xil kadrni takrorlama. Birinchi sahna kuchli hook, "
                  "oxirgi sahnada hikoyaga mos qisqa CTA bo‘lsin: tomoshabinni videoni ulashish, izoh qoldirish "
                  "yoki keyingi qismni kutishga taklif qil. CTA ni voice va big matniga tabiiy kirit. "
                  "Bosh qahramonning ismi va ko‘rinishini alohida character "
                  "maydonida yoz. Rasmlarda yozuv yoki logo bo‘lmasin. Uslub: " + style + ".\n"
                  "FAQAT JSON: {\"title\":\"...\",\"hook\":\"...\",\"character\":\"...\",\"scenes\":[{\"voice\":\"...\","
                  "\"big\":\"...\",\"image\":\"...\",\"layout\":\"full\"}],\"caption\":\"...\","
                  "\"hashtags\":\"\",\"mood\":\"cinematic\"}\nG‘oya: " + idea[:1200])
        ready = [] if use_openai else daily_video._ready()
        story = service._ask_json(prompt, ready, 240)
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
        story_video.design_plan(story, ready)
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
        _update(job_id, status="images", message="Qahramon va sahna rasmlari ChatGPT’da yaratilmoqda…", story=story)
        width, height = ((1920, 1080) if fmt == "16:9" else (1080, 1080) if fmt == "1:1" else (1080, 1920))
        size = (width, height)

        def generate_image(prompt: str) -> bytes:
            if use_openai:
                return providers._openai_image(prompt, "medium", size)
            return account_images.generate(prompt, size)

        portrait = folder / "qahramon.png"
        portrait.write_bytes(generate_image(portrait_prompt))
        _update(job_id, character=f"/api/creative-video/{job_id}/character", message="Qahramon tayyor. Sahnalar chizilmoqda…")
        image_paths = []
        for index, scene in enumerate(story["scenes"]):
            prompt = f"{style} illustration. Main character (keep this exact design in every scene): {character}. Scene: {scene.get('image', '')}. Story idea: {idea}. No text, no watermark."
            path = folder / f"scene-{index + 1}.png"
            path.write_bytes(generate_image(prompt))
            image_paths.append(str(path))
            _update(job_id, message=f"Sahna rasmlari yaratilmoqda… {index + 1}/{len(story['scenes'])}")
        _update(job_id, status="rendering", message="Diktor ovozi va videoni yig‘yapman…")
        scenes = [{"title": scene.get("big") or scene.get("voice", "")[:65],
                   "text": scene.get("big", ""), "narration": scene.get("voice", ""),
                   "image_prompt": scene.get("image", ""), "duration": 4}
                  for scene in story["scenes"]]
        video = outbox.new_path(f"multik_{job_id}", "mp4")
        from .plugins.video_studio import make_content_video
        result = make_content_video(topic=idea, scenes=scenes, format=fmt, platform="reels",
                                    voice=True, ai_images=False, images=image_paths, _output_path=video)
        if not video.is_file():
            raise RuntimeError(result or "MP4 fayli yaratilmadi")
        _update(job_id, status="done", message="Video tayyor", video=video.name,
                result=result, source=source, character=f"/api/creative-video/{job_id}/character")
    except Exception as error:
        log.exception("Creative video job failed")
        _update(job_id, status="error", message=str(error)[:500])


def character_path(job_id: str) -> Path | None:
    folder = (config.data_dir / "creative_videos" / job_id).resolve()
    path = folder / "qahramon.png"
    if folder.parent == (config.data_dir / "creative_videos").resolve() and path.is_file() and not path.is_symlink():
        return path
    return None
