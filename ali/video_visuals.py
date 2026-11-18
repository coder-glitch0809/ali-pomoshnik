"""Seeded SVG scenery, also usable as a translucent overlay on footage."""
import math
import random
import re


VISUAL_CSS = """
.procedural-visual{position:absolute;inset:0;overflow:hidden;pointer-events:none}
.procedural-visual>svg{width:100%;height:100%;display:block}
.procedural-visual.media-overlay{opacity:.22}
.procedural-drift{transform-origin:540px 960px}
@keyframes procedural-drift{from{transform:translate(-18px,12px) rotate(-3deg) scale(1.02)}
to{transform:translate(20px,-20px) rotate(4deg) scale(1.09)}}
"""


def palette(scene):
    """Only allow literal CSS hex colors from persisted or model-generated plans."""
    visual = scene.get("visual")
    colors = visual.get("palette") if isinstance(visual, dict) else None
    if not isinstance(colors, (list, tuple)) or len(colors) != 3:
        return ("#101b39", "#5fdacb", "#ffd080")
    return tuple(c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)
                 else default for c, default in zip(colors, ("#101b39", "#5fdacb", "#ffd080")))


def _number(value, default):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def scene_visual(scene, index, start, duration):
    """Return deterministic, frame-seekable scenery for a single scene."""
    visual = scene.get("visual")
    visual = visual if isinstance(visual, dict) else {}
    index = max(0, int(_number(index, 0)))
    seed = visual.get("seed", index)
    rng = random.Random(seed if isinstance(seed, (int, str)) else index)
    start = _number(start, 0)
    duration = max(.1, _number(duration, 3))
    dark, accent, light = palette(scene)
    uid = f"visual{index}"
    angle = rng.randint(0, 359)
    shapes = []
    background = visual.get("background", "aurora")
    if background == "grid":
        spacing = rng.randint(90, 160)
        shapes += [f'<path d="M{x} 0V1920"/>' for x in range(0, 1081, spacing)]
        shapes += [f'<path d="M0 {y}H1080"/>' for y in range(0, 1921, spacing)]
    elif background == "rings":
        cx, cy = rng.randint(100, 980), rng.randint(350, 1500)
        shapes += [f'<circle cx="{cx}" cy="{cy}" r="{r}"/>' for r in range(120, 1600, rng.randint(100, 180))]
    elif background == "ribbons":
        for y in range(-300, 2100, 280):
            bend = rng.randint(-300, 300)
            shapes.append(f'<path d="M-100 {y} Q540 {y + 700 + bend} 1180 {y + 100}" stroke-width="{rng.randint(20, 65)}"/>')
    else:
        for _ in range(6):
            shapes.append(f'<ellipse cx="{rng.randint(0, 1080)}" cy="{rng.randint(0, 1920)}" '
                          f'rx="{rng.randint(250, 650)}" ry="{rng.randint(200, 550)}" '
                          f'fill="url(#{uid}Glow)" stroke="none"/>')
    graphics = []
    graphic = visual.get("graphic", "dots")
    for _ in range(12):
        x, y = rng.randint(30, 1050), rng.randint(60, 1860)
        if graphic == "orbits":
            graphics.append(f'<circle cx="{x}" cy="{y}" r="{rng.randint(12, 90)}" fill="none"/>')
        elif graphic == "lines":
            graphics.append(f'<path d="M{x} {y}l{rng.randint(-120, 120)} {rng.randint(30, 200)}"/>')
        else:
            graphics.append(f'<circle cx="{x}" cy="{y}" r="{rng.randint(3, 14)}"/>')
    return (f'<div class="procedural-visual"><svg viewBox="0 0 1080 1920" preserveAspectRatio="xMidYMid slice" '
            f'aria-hidden="true"><defs><linearGradient id="{uid}Base" gradientTransform="rotate({angle} .5 .5)">'
            f'<stop stop-color="{dark}"/><stop offset="1" stop-color="{accent}"/></linearGradient>'
            f'<radialGradient id="{uid}Glow"><stop stop-color="{light}" stop-opacity=".65"/>'
            f'<stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs>'
            f'<path fill="url(#{uid}Base)" d="M0 0H1080V1920H0Z"/>'
            f'<g class="procedural-drift" style="animation:procedural-drift {duration:.3f}s ease-in-out {start:.3f}s both">'
            f'<g fill="none" stroke="{accent}" stroke-width="3" opacity=".55">{"".join(shapes)}</g>'
            f'<g fill="{light}" stroke="{light}" stroke-width="2" opacity=".45">{"".join(graphics)}</g>'
            '</g></svg></div>')
