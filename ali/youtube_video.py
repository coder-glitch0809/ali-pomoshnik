"""Landscape YouTube exports and restart-safe daily production (Tashkent time)."""
import json
import logging
import math
import re
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import config

log = logging.getLogger("ali.youtube_video")
TIMES = ("10:00", "13:00", "17:00")
# Tashkent is UTC+05:00 year-round; no OS timezone database dependency on Windows.
TZ = timezone(timedelta(hours=5), "Asia/Tashkent")
STATE = config.data_dir / "youtube_video.json"
_state_lock = threading.RLock()
_job_lock = threading.Lock()
_scheduled = set()
RETRY_SECONDS = 900


def enqueue(topic, notify):
    threading.Thread(target=run, args=("Buyurtma", notify, topic), daemon=True, name="youtube-order").start()
    return "YouTube video navbatga tushdi: 1920x1080, gapiruvchi personaj va alohida sahnalar. Tayyor fayl yuboriladi."


def handle_text(text, notify):
    from . import daily_video
    if not re.search(r"youtube|you\s*tube|ютуб", text or "", re.I):
        return ""
    if daily_video._WHERE.search(text) and (daily_video._ASK.search(text) or not daily_video._ORDER.search(text)):
        with _state_lock:
            state = _state()
        history = state.get("history", [])
        message = "YouTube jadvali: har kuni 10:00, 13:00, 17:00 (Asia/Tashkent)."
        if history:
            message += f"\nOxirgi tayyor video: {history[-1]['title']} ({history[-1]['at']})."
        if state.get("last_error"):
            message += f"\nOxirgi xato: {state['last_error']}"
        return message
    if daily_video._ORDER.search(text) and not daily_video._ASK.search(text):
        return enqueue(text, notify)
    return ""


def _state():
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("YouTube holati obyekt bo'lishi kerak")
        return value
    except FileNotFoundError:
        return {}


def _save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def quality_issues(path, duration=None):
    from .skills.video_edit import info
    meta = info(Path(path))
    issues = []
    if (meta["width"], meta["height"]) != (1920, 1080):
        issues.append("YouTube eksporti 1920x1080 bo'lishi kerak")
    if meta["fps"] < 29 or not meta["audio"]:
        issues.append("30 fps va diktor ovozi kerak")
    if not math.isfinite(meta["duration"]) or meta["duration"] < 5:
        issues.append("Video juda qisqa yoki buzilgan")
    if duration is not None and abs(meta["duration"] - duration) > .5:
        issues.append("Video davomiyligi diktor ovoziga mos emas")
    return issues


def make(slot="Buyurtma", notify=lambda text: None, topic=""):
    from . import daily_video, outbox, story_video, video_variety, youtube_content, youtube_render
    from .skills import presenter, talking_head
    from .skills.video_edit import _run

    with _state_lock:
        history = _state().get("history", [])[-60:]
    data = youtube_content.script(history, daily_video._ready(), topic)
    scenes = data["scenes"]
    video_variety.direction(data, history)
    # The landscape renderer scales the established presenter rig into its safe zone.
    character = daily_video.character()
    rig = (presenter.build(character) if character else None) or presenter.vector_rig()
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        voice, lengths = story_video.voices(scenes, folder)
        starts = [sum(lengths[:index]) for index in range(len(scenes))]
        duration = sum(lengths)
        used, reused = set(), {}
        for index, scene in enumerate(scenes):
            asset = video_variety.select_media(scene, used)
            if asset:
                if asset.suffix.lower() in {".mp4", ".mov"}:
                    clip = folder / f"archive{index}.mp4"
                    _run(["-i", str(asset), "-t", str(lengths[index]), "-an", "-vf",
                          "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1",
                          "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(clip)])
                    asset = clip
                reused[index] = (asset, "egasi arxivi")
        missing = [index for index in range(len(scenes)) if index not in reused]
        generated = iter(story_video.images([scenes[index] for index in missing], data.get("seed", 7),
                                             size=(1920, 1080)))
        pics = [reused[index] if index in reused else next(generated) for index in range(len(scenes))]
        html, subs = youtube_render.page(data, starts, lengths, pics, rig)
        mouth = talking_head.levels(voice, duration, 30)
        frames = story_video.host_frames(scenes, starts, lengths, 30, mouth, talking_head.blinks(duration, 30))
        raw = folder / "landscape.mp4"
        story_video.render(html, raw, duration, frames, subs, viewport=(1920, 1080))
        final = folder / "finished.mp4"
        _run(["-i", str(raw), "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
              "-c:v", "copy", "-af", f"apad=whole_dur={duration:.3f}", "-t", f"{duration:.3f}",
              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(final)])
        issues = quality_issues(final, duration)
        if issues:
            raise RuntimeError("; ".join(issues))
        output = outbox.new_path("youtube_" + str(data.get("title", slot)), "mp4")
        import shutil
        shutil.copy2(final, output)
        metadata = output.with_suffix(".json")
        chapters = []
        for scene, start in zip(scenes, starts):
            section = scene.get("section", "")
            if not chapters or chapters[-1]["section"] != section:
                chapters.append({"section": section, "start": round(start, 3)})
        metadata.write_text(json.dumps({**data, "duration": duration, "chapters": chapters},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    outbox.register(output)
    return {"path": str(output), "idea": data, "duration": duration,
            "sources": "YouTube 1920x1080, H.264, AAC 48 kHz, har sahna uchun yangi vizual reja"}


def run(slot, notify=lambda text: None, topic="", key=None):
    """Persist completion only after validation; failures become eligible after 15 minutes."""
    from . import daily_video, studio_flow
    with _job_lock:
        try:
            with _state_lock:
                if key and key in _state().get("done", {}):
                    return
            with daily_video._lock:
                result = make(slot, notify, topic)
                issues = quality_issues(result["path"], result.get("duration"))
                if issues:
                    raise RuntimeError("; ".join(issues))
            now = datetime.now(TZ)
            data = result["idea"]
            with _state_lock:
                state = _state()
                state.setdefault("history", []).append({"title": data.get("title", ""),
                    "topic": data.get("topic", ""), "style": data.get("style", ""),
                    "script": " ".join(s.get("voice", "") for s in data["scenes"]),
                    "path": result["path"], "at": now.isoformat(), "visual_id": data.get("visual_id", "")})
                state["history"] = state["history"][-60:]
                if key:
                    state.setdefault("done", {})[key] = result["path"]
                    state["done"] = dict(list(state["done"].items())[-90:])
                    state.setdefault("retry", {}).pop(key, None)
                state["last_error"] = ""
                _save(state)
        except Exception as error:
            log.exception("YouTube video yasalmadi")
            with _state_lock:
                state = _state()
                state["last_error"] = str(error)[:400]
                if key:
                    state.setdefault("retry", {})[key] = datetime.now(TZ).timestamp() + RETRY_SECONDS
                    state["retry"] = dict(list(state["retry"].items())[-90:])
                _save(state)
            notify(f"{slot} YouTube video yasalmadi: {str(error)[:300]}")
            return
        finally:
            with _state_lock:
                _scheduled.discard(key)
    text = f"{slot} YouTube video tayyor: {data.get('title', '')}\n{result['path']}\n{result['sources']}"
    path = Path(result["path"])
    files = [str(path)] if path.stat().st_size <= 45 * 1024 * 1024 else []
    if not files:
        text += "\nAsl sifatdagi fayl mahalliy saqlandi; hajmi Telegram bot chegarasidan katta."
    try:
        studio_flow.send_files(text, files)
        notify(text)
    except Exception:
        log.exception("YouTube natija xabari yuborilmadi; tayyor fayl saqlandi")


def tick(notify, now=None):
    """Catch up today's due slots once, including after restart; never mark failed jobs done."""
    now = now or datetime.now(TZ)
    now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    with _state_lock:
        state = _state()
        for slot in TIMES:
            hour, minute = map(int, slot.split(":"))
            at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            key = f"{now.date().isoformat()} {slot}"
            if (now < at or key in state.get("done", {}) or key in _scheduled
                    or state.get("retry", {}).get(key, 0) > now.timestamp()):
                continue
            _scheduled.add(key)
            try:
                threading.Thread(target=run, args=(slot, notify), kwargs={"key": key},
                                 daemon=True, name="youtube-video").start()
            except Exception:
                _scheduled.discard(key)
                raise
