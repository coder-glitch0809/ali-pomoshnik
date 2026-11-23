"""Offline editorial illustrations from the existing topic-aware SVG artwork.

These are labelled illustrations, never presented as photographs or client results.
The same asset path is used by Reels, Shorts and landscape exports.
"""
import hashlib
import html
from pathlib import Path

from .skills import motion_bg, stage
from .video_visuals import palette


def page(scene, size):
    width, height = size
    dark, accent, light = palette(scene)
    icon = motion_bg.pick({"big": scene.get("big", ""), "small": scene.get("voice", "")}, [])
    heading = html.escape(str(scene.get("big") or "Amaliy maslahat"))
    landscape = width > height
    art = stage._backdrop(stage.backdrop_of(icon), "none")
    symbol = motion_bg._icon(icon, 0, True)
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    *{{box-sizing:border-box}}body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;
    background:radial-gradient(ellipse at 70% 30%,{accent},{dark} 80%);color:{light};font-family:Arial,sans-serif}}
    .scenery{{position:absolute;inset:0;opacity:.65}}.scenery .bd{{position:absolute;right:0;bottom:0}}
    .label{{position:absolute;left:7%;top:8%;font-size:24px;letter-spacing:5px}}
    .card{{position:absolute;left:8%;top:24%;width:{'42' if landscape else '84'}%;height:49%;
    border:2px solid {accent};border-radius:48px;background:{dark}dd;box-shadow:0 35px 80px #0006;
    display:flex;align-items:center;justify-content:center}}
    {motion_bg.CSS}.mg{{position:relative;opacity:1;width:74%;height:74%}}
    .mg svg *{{animation:none!important;stroke-dashoffset:0!important;opacity:1}}
    h1{{position:absolute;left:{'56' if landscape else '9'}%;top:{'30' if landscape else '76'}%;
    width:{'37' if landscape else '82'}%;font-size:{'76' if landscape else '70'}px;line-height:1.1;
    margin:0;overflow-wrap:anywhere;text-shadow:0 4px 20px #000}}
    </style></head><body><div class="scenery">{art}</div>
    <div class="label">PLANET PRINT / ILLUSTRATSIYA</div><div class="card"><div class="mg">{symbol}</div></div>
    <h1>{heading}</h1></body></html>'''


def illustrate(scenes, folder, size=(1080, 1920)):
    """Render all missing illustrations in one browser; validate before returning."""
    from playwright.sync_api import sync_playwright
    from .browser import CHROME
    from .story_video import good

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME if Path(CHROME).exists() else None)
        try:
            tab = browser.new_page(viewport={"width": size[0], "height": size[1]})
            for scene in scenes:
                document = page(scene, size)
                path = folder / ("illustration_" + hashlib.sha256(document.encode()).hexdigest()[:20] + ".jpg")
                if not path.exists() or not good(path.read_bytes()):
                    tab.set_content(document, wait_until="load")
                    tab.evaluate("document.getAnimations().forEach(a => {a.pause();a.currentTime=2000})")
                    data = tab.screenshot(type="jpeg", quality=94)
                    if not good(data):
                        raise RuntimeError("Mavzuli illustratsiya tekshiruvdan o'tmadi")
                    path.write_bytes(data)
                outputs.append(path)
        finally:
            browser.close()
    return outputs
