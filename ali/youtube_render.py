"""Native landscape chapter layouts for narrated YouTube videos."""
import base64
import html
import math
import random
from pathlib import Path

from .video_visuals import VISUAL_CSS, palette, scene_visual


CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#080d19;color:white}
body{font-family:Arial,sans-serif}.yt-scene{position:absolute;inset:0;visibility:hidden;overflow:hidden}
.yt-scene>.procedural-visual{opacity:.65}.yt-shade{position:absolute;inset:0;background:linear-gradient(90deg,#000b,transparent 85%),radial-gradient(ellipse,transparent 45%,#0008)}
.yt-media{position:absolute;left:820px;top:145px;width:1010px;height:700px;overflow:hidden;border-radius:28px;box-shadow:0 30px 100px #0008}
.yt-media .bg{width:100%;height:100%;object-fit:contain;transform-origin:center;background:#101725}
.yt-copy{position:absolute;left:105px;top:290px;width:640px}.yt-copy h1{font-size:68px;line-height:1.12;letter-spacing:-2px;margin:25px 0;overflow-wrap:anywhere}
.yt-copy .eyebrow{color:var(--accent);font-size:23px;letter-spacing:5px;text-transform:uppercase}
.yt-copy p{font-size:28px;line-height:1.5;color:#e1e6ed;max-height:190px;overflow:hidden}
.yt-scene.right .yt-media{left:90px}.yt-scene.right .yt-copy{left:1170px}
.yt-scene.full .yt-media{inset:0;width:1920px;height:1080px;border-radius:0;opacity:.58}
.yt-scene.full .yt-copy{top:320px;left:140px;width:1150px}.yt-scene.full .yt-copy h1{font-size:90px}
.yt-scene.has-host .yt-copy{max-width:1050px}.yt-scene.has-host .yt-media{width:650px;left:750px}
.yt-scene.full.has-host .yt-media{left:0;width:1920px;height:1080px;opacity:.82}
.yt-scene.full.has-host .yt-copy{width:1050px;text-shadow:0 3px 18px #000}
.yt-chapter{position:absolute;left:105px;top:65px;font-size:25px;letter-spacing:2px;max-width:1500px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}
.yt-chapter b{color:var(--accent);margin-right:25px}.yt-line{position:absolute;left:105px;top:115px;width:90px;height:4px;background:var(--accent)}
.yt-caption{position:absolute;left:210px;right:210px;bottom:65px;text-align:center;z-index:1000;font-size:38px;line-height:1.35;visibility:hidden}
.yt-caption>div{display:inline-block;max-width:1450px;padding:14px 28px;background:#050b18e8;border-radius:16px;box-shadow:0 8px 35px #0006}
.yt-caption span{display:inline-block;margin:0 5px}.yt-caption .on{color:#ffe0a0}
.yt-progress{position:absolute;left:0;bottom:0;height:5px;background:#fff8;transform-origin:left;z-index:1001;width:100%}
.yt-host{position:absolute;right:40px;bottom:160px;width:580px;height:620px;overflow:hidden;z-index:800;pointer-events:none}
.yt-host-stage{position:absolute;left:-40px;top:-620px;width:1080px;height:1920px;transform:scale(.65);transform-origin:top left}
@keyframes yt-active{0%,99.999%{visibility:visible}100%{visibility:hidden}}
@keyframes yt-fade{from{opacity:0}to{opacity:1}}
@keyframes yt-slide{from{opacity:0;transform:translateX(55px)}to{opacity:1;transform:translateX(0)}}
@keyframes yt-zoom{from{opacity:0;transform:scale(1.06)}to{opacity:1;transform:scale(1)}}
@keyframes yt-pan{from{transform:scale(1.08) translateX(-2%)}to{transform:scale(1.14) translateX(2%)}}
@keyframes yt-pull{from{transform:scale(1.16)}to{transform:scale(1.04)}}
@keyframes yt-progress{from{transform:scaleX(0)}to{transform:scaleX(1)}}
"""


def page(data, starts, lengths, pics, rig=None):
    """Return 1920x1080 HTML and word timings for story_video's frame renderer."""
    scenes = data.get("scenes", [])
    if not scenes or not (len(scenes) == len(starts) == len(lengths) == len(pics)):
        raise ValueError("YouTube scenes, timing and media must have matching lengths")
    if any(not math.isfinite(float(t)) or float(t) < 0 for t in starts) or any(
            not math.isfinite(float(t)) or float(t) <= 0 for t in lengths):
        raise ValueError("Invalid YouTube scene timing")
    duration = starts[-1] + lengths[-1]
    parts, subtitles = [], []
    previous_layout = None
    for index, (scene, start, length, pic) in enumerate(zip(scenes, starts, lengths, pics)):
        base, accent, _ = palette(scene)
        visual = scene.get("visual") if isinstance(scene.get("visual"), dict) else {}
        rng = random.Random(str(visual.get("seed", index)))
        layouts = ("left", "full") if rig else ("left", "right", "full")
        layout = rng.choice([value for value in layouts if value != previous_layout])
        previous_layout = layout
        transition = {"t_slide": "yt-slide", "slide": "yt-slide", "t_zoom": "yt-zoom", "zoom": "yt-zoom"}.get(
            scene.get("transition"), rng.choice(("yt-fade", "yt-slide", "yt-zoom")))
        motion = rng.choice(("yt-pull", "yt-pan"))
        art = scene_visual(scene, index, start, length)
        media = ""
        asset = pic[0] if isinstance(pic, (tuple, list)) else pic
        if asset:
            path = Path(asset)
            suffix = path.suffix.lower()
            video = suffix in {".mp4", ".mov", ".webm"}
            mime = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
            uri = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
            try:
                speed = float(scene.get("speed", .65 if index % 3 == 1 else 1))
            except (ValueError, TypeError):
                speed = 1
            speed = max(.35, min(1, speed)) if math.isfinite(speed) else 1
            attrs = f' data-start="{start}" data-speed="{speed}" muted preload="auto"' if video else ""
            tag = "video" if video else "img"
            media = (f'<div class="yt-media"><{tag} class="bg" src="{uri}"{attrs} '
                     f'style="animation:{motion} {length:.3f}s linear {start:.3f}s both">'
                     + ('</video>' if video else '') + '</div>')
        section = scene.get("section", "")
        section = {"hook": "Boshlanish", "problem": "Muammo", "demonstration": "Amaliy misol",
                   "solution": "Yechim", "cta": "Keyingi qadam"}.get(section, section)
        chapter = html.escape(str(scene.get("chapter") or section or data.get("title") or "YouTube"))
        heading = html.escape(str(scene.get("big") or scene.get("title") or data.get("title") or ""))
        summary = html.escape(str(scene.get("summary") or ""))
        host_class = " has-host" if rig else ""
        parts.append(f'<section class="yt-scene {layout}{host_class}" style="--accent:{accent};background:{base};z-index:{index + 1};'
                     f'animation:yt-active {length:.3f}s linear {start:.3f}s forwards,'
                     f'{transition} .35s ease-out {start:.3f}s both">{art}{media}<div class="yt-shade"></div>'
                     f'<div class="yt-chapter"><b>{index + 1:02d}</b>{chapter}</div><div class="yt-line"></div>'
                     f'<div class="yt-copy" style="animation:{transition} .35s ease-out {start:.3f}s both">'
                     f'<div class="eyebrow">{html.escape(str(data.get("series") or ""))}</div><h1>{heading}</h1>'
                     f'<p>{summary}</p></div></section>')
        words = str(scene.get("voice") or "").split()
        total = sum(map(len, words)) or 1
        cursor = start
        for group in range(0, len(words), 9):
            chunk = words[group:group + 9]
            span = length * sum(map(len, chunk)) / total
            caption = []
            for word_index, word in enumerate(chunk, group):
                uid = f"ytw{index}_{word_index}"
                word_span = length * len(word) / total
                subtitles.append((cursor, cursor + word_span, uid))
                cursor += word_span
                caption.append(f'<span id="{uid}">{html.escape(word)}</span>')
            parts.append(f'<div class="yt-caption" style="animation:yt-active {span:.4f}s linear {cursor - span:.4f}s forwards">'
                         f'<div>{"".join(caption)}</div></div>')
    if rig:
        from .skills import presenter
        parts.append('<div class="yt-host"><div class="yt-host-stage">' + presenter.html(rig) + '</div></div>')
    parts.append(f'<div class="yt-progress" style="animation:yt-progress {duration:.3f}s linear both"></div>')
    script = """<script>window.__subs=function(on){document.querySelectorAll('.yt-caption .on').forEach(e=>e.classList.remove('on'));
for(const id of on){const e=document.getElementById(id);if(e)e.classList.add('on');}};</script>"""
    return ('<!doctype html><html><head><meta charset="utf-8"><style>' + CSS + VISUAL_CSS + '</style></head><body>'
            + ''.join(parts) + script + '</body></html>'), subtitles


def render(html, out, dur, frames=None, subs=None, fps=30):
    from . import story_video
    neutral = {"x": 160, "ty": 0, "tr": 0, "sc": 1, "h": 0, "n": 0, "m": 0, "b": False, "a": ""}
    return story_video.render(html, out, dur, frames or [neutral], subs or [], fps=fps, viewport=(1920, 1080))
