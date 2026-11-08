"""Dizayner uchun universal fayl vositalari: PDF (matn/jadval/rasm), rasmlarni PDF'ga yig'ish va 3D brending.

- make_pdf        - istalgan matn/jadval/rasmdan A4 PDF (brendbuk, taklif, texnik topshiriq, katalog).
- images_to_pdf   - PNG/JPG rasmlar va tayyor PDF'larni bitta PDF'ga yig'adi.
- design_brand_3d - brend nomidan hajmli (3D) harflar: .obj+.mtl (3ds Max), .dxf (AutoCAD: MESH + kontur) va PNG ko'rinish.
Fayllar outbox'ga yoziladi va foydalanuvchiga avtomatik yuboriladi.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import outbox
from . import skill
from .brandbook import _clean, _font, _hex, _light, _mix, _wrap

PW, PH = 1240, 1754  # A4 tik, 150 dpi
MARGIN = 120


# ------------------------------------------------------------------ make_pdf
class _Doc:
    """Sahifalab chizadigan oddiy PDF yig'uvchi (Pillow)."""

    def __init__(self, title: str, color: str):
        self.title, self.color = title, color
        self.dark = _mix(color, "#000000", .78)
        self.pages = []
        self.img = self.d = None
        self.y = 0
        self.new_page()

    def new_page(self):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (PW, PH), "#FFFFFF")
        self.d = ImageDraw.Draw(self.img)
        self.pages.append(self.img)
        self.d.text((MARGIN, 60), self.title[:60], font=_font(20), fill=_mix(self.dark, "#FFFFFF", .55))
        self.d.line([(MARGIN, 96), (PW - MARGIN, 96)], fill=_mix(self.dark, "#FFFFFF", .85), width=2)
        self.d.text((PW - MARGIN, PH - 60), str(len(self.pages)), font=_font(20), fill=_mix(self.dark, "#FFFFFF", .55), anchor="rs")
        self.y = 150

    def room(self, need: int):
        if self.y + need > PH - 130:
            self.new_page()

    def text(self, text: str, size=28, bold=False, fill=None, indent=0, gap=1.5, after=14):
        font = _font(size, bold)
        lines = _wrap(self.d, text, font, PW - 2 * MARGIN - indent)
        for line in lines:
            self.room(int(size * gap))
            self.d.text((MARGIN + indent, self.y), line, font=font, fill=fill or self.dark)
            self.y += int(size * gap)
        self.y += after

    def heading(self, text: str, level: int = 1):
        size = 44 if level == 1 else 34
        self.room(size * 3)
        self.y += 18
        self.text(text, size, True, self.color if level == 1 else self.dark, after=10)

    def bullet(self, text: str, mark: str):
        font = _font(28)
        lines = _wrap(self.d, text, font, PW - 2 * MARGIN - 60)
        self.room(int(28 * 1.5) * len(lines))
        self.d.text((MARGIN + 10, self.y), mark, font=_font(28, True), fill=self.color)
        for line in lines:
            self.d.text((MARGIN + 60, self.y), line, font=font, fill=self.dark)
            self.y += 42
        self.y += 6

    def table(self, rows: list[list[str]]):
        cols = max(len(r) for r in rows)
        cw = (PW - 2 * MARGIN) // cols
        font, bold = _font(24), _font(24, True)
        for i, row in enumerate(rows):
            cells = [_wrap(self.d, row[c] if c < len(row) else "", bold if i == 0 else font, cw - 24) or [""]
                     for c in range(cols)]
            h = max(len(c) for c in cells) * 34 + 20
            self.room(h)
            head = i == 0
            self.d.rectangle([MARGIN, self.y, PW - MARGIN, self.y + h],
                             fill=self.color if head else (_mix(self.color, "#FFFFFF", .92) if i % 2 == 0 else "#FFFFFF"),
                             outline=_mix(self.dark, "#FFFFFF", .8))
            ink = "#111111" if head and _light(self.color) else ("#FFFFFF" if head else self.dark)
            for c, lines in enumerate(cells):
                for k, line in enumerate(lines):
                    self.d.text((MARGIN + c * cw + 12, self.y + 10 + k * 34), line, font=bold if head else font, fill=ink)
            self.y += h
        self.y += 24

    def image(self, path: str, caption: str = ""):
        from PIL import Image
        p = Path(path).expanduser()
        if not p.is_file():
            self.text(f"[rasm topilmadi: {p.name}]", 22, fill="#DC2626")
            return
        try:
            im = Image.open(p).convert("RGBA")
        except Exception:
            self.text(f"[rasm ochilmadi: {p.name}]", 22, fill="#DC2626")
            return
        im.thumbnail((PW - 2 * MARGIN, 900))
        self.room(im.height + 60)
        self.img.paste(im, (MARGIN, self.y), im)
        self.y += im.height + 12
        if caption:
            self.text(caption, 22, fill=_mix(self.dark, "#FFFFFF", .4), after=16)
        else:
            self.y += 16

    def cover(self, subtitle: str):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (PW, PH), self.color)
        d = ImageDraw.Draw(img)
        ink = "#111111" if _light(self.color) else "#FFFFFF"
        d.rectangle([MARGIN, 640, MARGIN + 160, 652], fill=ink)
        font = _font(88, True)
        y = 700
        for line in _wrap(d, self.title, font, PW - 2 * MARGIN):
            d.text((MARGIN, y), line, font=font, fill=ink)
            y += 110
        if subtitle:
            for line in _wrap(d, subtitle, _font(36), PW - 2 * MARGIN):
                d.text((MARGIN, y + 20), line, font=_font(36), fill=_mix(ink, self.color, .25))
                y += 52
        self.pages.insert(0, img)


@skill(
    description=(
        "Istalgan mazmundan tayyor A4 PDF fayl yaratadi: brend taklifi, brendbuk matni, texnik topshiriq, katalog, narxlar "
        "jadvali, rasmlar bilan hisobot. make_brandbook ishlamasa yoki brend hujjatini PDF qilish kerak bo'lsa - shuni "
        "ishlating (matn javobda qolib ketmasin, FAYL bering). sections: [{heading, level (1|2), paragraphs: [...], "
        "bullets: [...], numbered: [...], table: [[sarlavhalar], [qator]...], images: [{path, caption}]}]. "
        "Fayl AVTOMATIK yuboriladi."
    ),
    params={
        "title": {"type": "string", "description": "Hujjat nomi"},
        "subtitle": {"type": "string", "description": "Kichik sarlavha (muqovada)"},
        "sections": {"type": "array", "items": {"type": "object"}, "description": "Bo'limlar"},
        "color": {"type": "string", "description": "Brend rangi, hex (standart #1E3A8A)"},
        "cover": {"type": "boolean", "description": "Rangli muqova sahifasi (standart true)"},
    },
    required=["title", "sections"],
)
def make_pdf(title: str, sections: list, subtitle: str = "", color: str = "#1E3A8A", cover: bool = True) -> str:
    title = _clean(title, 120) or "Hujjat"
    doc = _Doc(title, _hex(color, "#1E3A8A"))
    for raw in (sections or [])[:80]:
        if not isinstance(raw, dict):
            continue
        if raw.get("heading"):
            doc.heading(_clean(raw["heading"], 200), 2 if raw.get("level") == 2 else 1)
        for key in ("paragraphs", "bullets", "numbered"):
            val = raw.get(key)
            items = [v for v in re.split(r"\n+", val) if v.strip()] if isinstance(val, str) else (val or [])
            for n, text in enumerate([_clean(v, 600) for v in items if _clean(v)][:80], 1):
                if key == "paragraphs":
                    doc.text(text)
                else:
                    doc.bullet(text, "•" if key == "bullets" else f"{n}.")
        rows = raw.get("table")
        if isinstance(rows, list) and rows and all(isinstance(r, list) for r in rows):
            doc.table([[_clean(c, 200) for c in r[:8]] for r in rows[:150]])
        for im in (raw.get("images") or [])[:10]:
            if isinstance(im, dict) and im.get("path"):
                doc.image(str(im["path"]), _clean(im.get("caption"), 200))
            elif isinstance(im, str):
                doc.image(im)
    if cover:
        doc.cover(_clean(subtitle, 200))
    path = outbox.new_path(title, "pdf")
    doc.pages[0].save(path, save_all=True, append_images=doc.pages[1:], resolution=150)
    outbox.register(path)
    return f"✅ PDF tayyor: {path.name} ({len(doc.pages)} sahifa). Fayl avtomatik yuboriladi."


# ------------------------------------------------------------------ images_to_pdf
@skill(
    description=(
        "PNG/JPG rasmlarni (va tayyor PDF fayllarni) bitta PDF'ga yig'adi: maketlar, banner variantlari, brend fayllari "
        "to'plami. paths - fayllarning to'liq yo'llari, tartib bo'yicha."
    ),
    params={
        "paths": {"type": "array", "items": {"type": "string"}, "description": "Rasm yoki PDF fayllar yo'llari"},
        "title": {"type": "string", "description": "Natija fayl nomi"},
    },
    required=["paths"],
)
def images_to_pdf(paths: list, title: str = "Maketlar") -> str:
    from PIL import Image
    from pypdf import PdfWriter
    files = [Path(str(p)).expanduser() for p in (paths or [])[:60]]
    missing = [p.name for p in files if not p.is_file()]
    files = [p for p in files if p.is_file()]
    if not files:
        return "Fayl topilmadi: " + (", ".join(missing) or "yo'l berilmadi")
    out = outbox.new_path(_clean(title, 60) or "Maketlar", "pdf")
    tmp: list[Path] = []
    writer = PdfWriter()
    try:
        for i, p in enumerate(files):
            if p.suffix.lower() == ".pdf":
                writer.append(str(p))
                continue
            im = Image.open(p)
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "#FFFFFF")
            bg.paste(im, mask=im.split()[3])
            one = out.with_name(f"{out.stem}_{i}.tmp.pdf")
            bg.save(one, resolution=150)
            tmp.append(one)
            writer.append(str(one))
        with open(out, "wb") as f:
            writer.write(f)
    finally:
        writer.close()
        for t in tmp:
            t.unlink(missing_ok=True)
    outbox.register(out)
    note = f" (topilmadi: {', '.join(missing)})" if missing else ""
    return f"✅ PDF yig'ildi: {out.name} - {len(files)} fayl{note}. Avtomatik yuboriladi."


# ------------------------------------------------------------------ 3D brending
def _glyph_rings(lines: list[str], height_mm: float):
    """Matnni vektor konturlarga aylantiradi: [(tashqi_halqa, [teshiklar])...] - mm."""
    import numpy as np
    from matplotlib.font_manager import FontProperties
    from matplotlib.path import Path as MPath
    from matplotlib.textpath import TextPath

    rings: list[list[tuple[float, float]]] = []
    for n, line in enumerate(lines):
        if not line.strip():
            continue
        tp = TextPath((0, 0), line, size=height_mm, prop=FontProperties(weight="bold"))
        verts = tp.vertices.copy()
        verts[:, 1] -= n * height_mm * 1.35
        shifted = MPath(verts, tp.codes)
        rings += [p.tolist() for p in shifted.to_polygons(closed_only=True) if len(p) >= 4]
    cleaned = []
    for r in rings:
        pts = [tuple(p) for p in r]
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) >= 3:
            cleaned.append(np.array(pts))
    # har bir halqa nechta halqa ichida - juft chuqurlik tashqi kontur, toq chuqurlik teshik
    out = []
    depth = []
    for i, r in enumerate(cleaned):
        d = sum(1 for j, o in enumerate(cleaned) if j != i and MPath(o).contains_point(r[0]))
        depth.append(d)
    for i, r in enumerate(cleaned):
        if depth[i] % 2 == 0:
            holes = [h for j, h in enumerate(cleaned)
                     if depth[j] == depth[i] + 1 and MPath(r).contains_point(h[0])]
            out.append((r, holes))
    return out


def _area(ring) -> float:
    import numpy as np
    x, y = ring[:, 0], ring[:, 1]
    return float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum() / 2)


def _orient(ring, ccw: bool):
    return ring if (_area(ring) > 0) == ccw else ring[::-1]


def build_extrusion(lines: list[str], height_mm: float, depth_mm: float, plate: bool):
    """Hajmli harflar to'ri: [(material, [uchlar...])...] (mm) va halqalar ro'yxati (kontur uchun)."""
    from ezdxf.math.triangulation import mapbox_earcut_2d

    groups = _glyph_rings(lines, height_mm)
    faces: list[tuple[str, list[tuple[float, float, float]]]] = []
    contours: list = []
    xs: list[float] = []
    ys: list[float] = []
    for outer, holes in groups:
        outer = _orient(outer, True)
        holes = [_orient(h, False) for h in holes]
        contours += [outer] + holes
        xs += outer[:, 0].tolist()
        ys += outer[:, 1].tolist()
        for tri in mapbox_earcut_2d([tuple(p) for p in outer], [[tuple(p) for p in h] for h in holes]):
            a, b, c = [(v.x, v.y) for v in tri]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0:
                b, c = c, b
            faces.append(("face", [(*a, depth_mm), (*b, depth_mm), (*c, depth_mm)]))
            faces.append(("back", [(*a, 0.0), (*c, 0.0), (*b, 0.0)]))
        for ring in [outer] + holes:
            n = len(ring)
            for i in range(n):
                p, q = ring[i], ring[(i + 1) % n]
                faces.append(("side", [(p[0], p[1], 0.0), (q[0], q[1], 0.0), (q[0], q[1], depth_mm), (p[0], p[1], depth_mm)]))
    if not faces:
        return [], [], (0, 0, 0, 0)
    box = (min(xs), min(ys), max(xs), max(ys))
    if plate:
        pad, t = height_mm * .25, max(depth_mm * .3, 4.0)
        x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        z0, z1 = -t, 0.0
        v = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        faces.append(("plate", [(*v[0], z0), (*v[3], z0), (*v[2], z0), (*v[1], z0)]))
        faces.append(("plate", [(*v[0], z1), (*v[1], z1), (*v[2], z1), (*v[3], z1)]))
        for i in range(4):
            p, q = v[i], v[(i + 1) % 4]
            faces.append(("plate", [(p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], z1), (p[0], p[1], z1)]))
        box = (x0, y0, x1, y1)
    return faces, contours, box


def _write_obj(faces, obj: Path, mtl: Path, colors: dict[str, str]) -> None:
    lines = [f"# Ali dizayner: hajmli brending (metr; harflar XY tekisligida, chuqurlik Z o'qida)",
             f"mtllib {mtl.name}"]
    verts: list[str] = []
    body: list[str] = []
    cur = None
    idx = 0
    for mat, pts in faces:
        if mat != cur:
            body.append(f"usemtl {mat}")
            cur = mat
        ids = []
        for x, y, z in pts:
            verts.append(f"v {x / 1000:.5f} {y / 1000:.5f} {z / 1000:.5f}")
            idx += 1
            ids.append(str(idx))
        body.append("f " + " ".join(ids))
    obj.write_text("\n".join(lines + verts + body) + "\n", encoding="utf-8")
    out = []
    for mat, hx in colors.items():
        r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5))
        out.append(f"newmtl {mat}\nKd {r:.3f} {g:.3f} {b:.3f}\nKa {r * .3:.3f} {g * .3:.3f} {b * .3:.3f}\nKs 0.3 0.3 0.3\nNs 40\n")
    mtl.write_text("\n".join(out), encoding="utf-8")


def _write_dxf(faces, contours, box, path: Path, text: str, height_mm: float, depth_mm: float) -> None:
    import ezdxf
    from ezdxf.render import MeshBuilder
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    for name, color in (("HARF_3D", 7), ("KONTUR", 1), ("MATN", 3)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    mb = MeshBuilder()
    for _, pts in faces:
        mb.add_face(pts)
    mb.render_mesh(msp, dxfattribs={"layer": "HARF_3D"})
    for ring in contours:  # lazer/frezer kesish konturi (yassi, 2D)
        msp.add_lwpolyline([tuple(p) for p in ring], close=True, dxfattribs={"layer": "KONTUR"})
    msp.add_text(f"{text} | harf balandligi {height_mm:g} mm, qalinlik {depth_mm:g} mm",
                 dxfattribs={"layer": "MATN", "height": max(8.0, height_mm * .12), "insert": (box[0], box[1] - height_mm * .5)})
    doc.saveas(path)


def _render_png(faces, box, path: Path, colors: dict[str, str]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([-.4, .5, .75])
    light /= np.linalg.norm(light)
    groups = {"plate": ([], []), "letters": ([], [])}  # taglik alohida va pastda chiziladi
    for mat, pts in faces:
        p = np.array(pts)
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(n) == 0:
            continue
        n /= np.linalg.norm(n)
        k = .55 + .45 * max(0.0, float(n @ light))
        base = np.array([int(colors[mat][i:i + 2], 16) for i in (1, 3, 5)]) / 255
        polys, cols = groups["plate" if mat == "plate" else "letters"]
        polys.append([(x, -z, y) for x, y, z in pts])  # grafik: X, -chuqurlik (kamera old tomonda), balandlik
        cols.append(tuple(np.clip(base * k, 0, 1)))
    fig = plt.figure(figsize=(9, 5.5), dpi=140)
    ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
    for z, (polys, cols) in enumerate(groups.values()):
        if polys:
            ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolors="none", zorder=z + 1))
    w, h = box[2] - box[0], box[3] - box[1]
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(-w * .3, w * .3)
    ax.set_zlim(box[1], box[3])
    ax.set_box_aspect((w, w * .6, h))
    ax.view_init(elev=14, azim=-72)
    ax.set_axis_off()
    fig.subplots_adjust(-.1, -.15, 1.1, 1.15)
    fig.savefig(path, facecolor="#FFFFFF")
    plt.close(fig)


@skill(
    description=(
        "Brend nomi/shiori uchun HAJMLI (3D) harflar yaratadi - 3ds Max va AutoCAD uchun HAQIQIY fayllar: .obj+.mtl (3ds Max, "
        "Blender; rangli materiallar), .dxf (AutoCAD: 3D MESH + yassi lazer/frezer kesish konturi) va 3D ko'rinish PNG. "
        "Hajmli (bortma) harf, peshlavha, brend stendi, 3D logotip matni uchun. Fayllar AVTOMATIK yuboriladi. "
        "Keyin autocad_open (.dxf) yoki max_open_model (.obj) bilan dasturda ochish mumkin."
    ),
    params={
        "text": {"type": "string", "description": "Harflar matni (ko'p qator uchun \\n)"},
        "height_mm": {"type": "number", "description": "Bosh harf balandligi, mm (standart 300)"},
        "depth_mm": {"type": "number", "description": "Harf qalinligi (chuqurligi), mm (standart 60)"},
        "color": {"type": "string", "description": "Harf old tomoni rangi, hex (brend asosiy rangi)"},
        "side_color": {"type": "string", "description": "Harf yon devori rangi, hex (standart: old rangdan to'qroq)"},
        "plate": {"type": "boolean", "description": "Orqasida taglik (plita) qo'shish (standart false)"},
        "plate_color": {"type": "string", "description": "Taglik rangi, hex (standart #1F2937)"},
    },
    required=["text"],
)
def design_brand_3d(text: str, height_mm: float = 300, depth_mm: float = 60, color: str = "#1E3A8A",
                    side_color: str = "", plate: bool = False, plate_color: str = "#1F2937") -> str:
    lines = [_clean(l, 40) for l in str(text or "").replace("\\n", "\n").split("\n") if _clean(l, 40)][:4]
    if not lines:
        return "Harflar matni berilmadi."
    height = max(20.0, min(float(height_mm or 300), 3000.0))
    depth = max(3.0, min(float(depth_mm or 60), 500.0))
    front = _hex(color, "#1E3A8A")
    colors = {"face": front, "back": _mix(front, "#000000", .5), "side": _hex(side_color, _mix(front, "#000000", .35)),
              "plate": _hex(plate_color, "#1F2937")}
    faces, contours, box = build_extrusion(lines, height, depth, plate)
    if not faces:
        return "Harflar konturi chiqmadi - matnni tekshiring."
    base = outbox.new_path(f"{lines[0]} 3D", "obj")
    mtl, dxf, png = base.with_suffix(".mtl"), base.with_suffix(".dxf"), base.with_suffix(".png")
    _write_obj(faces, base, mtl, colors)
    _write_dxf(faces, contours, box, dxf, " / ".join(lines), height, depth)
    _render_png(faces, box, png, colors)
    for p in (base, mtl, dxf, png):
        outbox.register(p)
    return (f"✅ 3D brending tayyor: {' / '.join(lines)} - harf {height:g} mm, qalinlik {depth:g} mm, {len(faces)} yuza. "
            f"Fayllar avtomatik yuboriladi: {png.name} (ko'rinish), {base.name}+{mtl.name} (3ds Max/Blender, metr), "
            f"{dxf.name} (AutoCAD: qatlamlar HARF_3D - MESH, KONTUR - kesish konturi, mm). Ochish: max_open_model / autocad_open.")
