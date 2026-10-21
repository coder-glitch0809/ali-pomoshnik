"""Photoshop plagini: Adobe Photoshop'ni COM orqali boshqaradi (dizayn yaratish, fayl ochish, eksport).
Photoshop kerak bo'lganda avtomatik ochiladi."""
import json
import tempfile
from pathlib import Path

from .. import outbox
from ..config import config
from ..skills import skill
from . import Plugin
from ._desktop import find_progid, hex_rgb, ps_str, run_ps

_progid: str | None = None


def _start() -> tuple[bool, str]:
    global _progid
    _progid = find_progid("Photoshop.Application")
    if not _progid:
        return False, "Photoshop bu kompyuterda topilmadi"
    if config.plugins_open_apps:
        run_ps(f"$null = New-Object -ComObject {_progid}", timeout=240)
        return True, "Ishga tushirildi"
    return True, "Tayyor (kerak bo'lganda ochiladi)"


PLUGIN = Plugin(key="photoshop", name="Photoshop", icon="Ps", start=_start,
                description="Adobe Photoshop: banner, post, afisha yaratish, rasm ochish va eksport")


def _jsx(code: str, timeout: int = 300) -> str:
    """ExtendScript (JSX) kodini Photoshop'da bajaradi va natijasini qaytaradi."""
    if not _progid:
        raise RuntimeError("Photoshop topilmadi")
    with tempfile.NamedTemporaryFile("w", suffix=".jsx", delete=False, encoding="utf-8") as f:
        f.write("app.displayDialogs = DialogModes.NO;\n" + code)
        path = Path(f.name)
    try:
        return run_ps(
            f"$ps = New-Object -ComObject {_progid}\n"
            f"$code = Get-Content -Raw -Encoding UTF8 -LiteralPath {ps_str(path)}\n"
            "$r = $ps.DoJavaScript($code)\nif ($r -ne $null) { Write-Output $r }",
            timeout=timeout,
        )
    finally:
        path.unlink(missing_ok=True)


def _js_path(path: Path) -> str:
    return json.dumps(str(path).replace("\\", "/"))


def _hex(value, default):
    return "%02X%02X%02X" % hex_rgb(value, default)


@skill(
    description="Photoshop'da yangi dizayn (banner, post, afisha) yaratadi: fon rangi va matn qatlamlari. "
                "PSD (tahrirlash uchun) va PNG fayllar foydalanuvchiga yuboriladi, Photoshop'da ochiq qoladi.",
    params={
        "title": {"type": "string", "description": "Dizayn nomi"},
        "width": {"type": "integer", "description": "Kenglik, piksel (masalan Instagram post 1080)"},
        "height": {"type": "integer", "description": "Balandlik, piksel"},
        "background": {"type": "string", "description": "Fon rangi, hex (masalan #1E2A78)"},
        "texts": {
            "type": "array",
            "description": "Matnlar: [{text, x, y, size, color, font}] - x,y chap yuqori burchakdan piksel "
                           "(y - matn asos chizig'i), size piksel, color hex, font PostScript nomi (ixtiyoriy)",
            "items": {"type": "object"},
        },
    },
    required=["title", "width", "height"],
)
def photoshop_design(title: str, width: int, height: int, background: str = "#FFFFFF", texts: list | None = None) -> str:
    width, height = max(16, min(width, 12000)), max(16, min(height, 12000))
    items = []
    for t in texts or []:
        if not isinstance(t, dict) or not str(t.get("text", "")).strip():
            continue
        items.append({
            "text": str(t["text"])[:2000].replace("\n", "\r"),
            "x": float(t.get("x", width * 0.1)), "y": float(t.get("y", height * 0.5)),
            "size": max(4.0, min(float(t.get("size", height / 12)), 2000.0)),
            "color": _hex(t.get("color"), "000000"), "font": str(t.get("font", ""))[:80],
        })
    base = outbox.new_path(title, "psd")
    png = base.with_suffix(".png")
    _jsx(f"""
app.bringToFront();
var oldR = app.preferences.rulerUnits, oldT = app.preferences.typeUnits;
app.preferences.rulerUnits = Units.PIXELS;
app.preferences.typeUnits = TypeUnits.PIXELS;
try {{
  var doc = app.documents.add({width}, {height}, 72, {json.dumps(title[:60])}, NewDocumentMode.RGB, DocumentFill.WHITE);
  var bg = new SolidColor(); bg.rgb.hexValue = "{_hex(background, 'FFFFFF')}";
  doc.selection.selectAll(); doc.selection.fill(bg); doc.selection.deselect();
  var items = {json.dumps(items)};
  for (var i = 0; i < items.length; i++) {{
    var it = items[i];
    var layer = doc.artLayers.add();
    layer.kind = LayerKind.TEXT;
    var t = layer.textItem;
    t.contents = it.text;
    t.size = it.size;
    if (it.font) {{ try {{ t.font = it.font; }} catch (e) {{}} }}
    var c = new SolidColor(); c.rgb.hexValue = it.color; t.color = c;
    t.position = [it.x, it.y];
  }}
  doc.saveAs(new File({_js_path(base)}), new PhotoshopSaveOptions(), true);
  doc.saveAs(new File({_js_path(png)}), new PNGSaveOptions(), true, Extension.LOWERCASE);
}} finally {{
  app.preferences.rulerUnits = oldR; app.preferences.typeUnits = oldT;
}}
""")
    made = [p for p in (base, png) if p.exists()]
    if not made:
        raise RuntimeError("Photoshop fayl saqlamadi")
    for p in made:
        outbox.register(p)
    return f"Dizayn tayyor ({width}x{height}): " + ", ".join(p.name for p in made)


@skill(
    description="Kompyuterdagi rasm yoki PSD faylni Photoshop'da ochadi.",
    params={"path": {"type": "string", "description": "Faylning to'liq yo'li"}},
)
def photoshop_open(path: str) -> str:
    file = Path(path).expanduser()
    if not file.is_file():
        return f"Fayl topilmadi: {path}"
    _jsx(f"app.bringToFront(); app.open(new File({_js_path(file)}));")
    return f"Photoshop'da ochildi: {file.name}"


@skill(
    description="Photoshop'dagi ochiq (faol) hujjatni faylga eksport qiladi va foydalanuvchiga yuboradi.",
    params={"format": {"type": "string", "enum": ["png", "jpg", "psd"], "description": "Fayl turi"}},
)
def photoshop_export(format: str = "png") -> str:
    name = _jsx("app.documents.length ? app.activeDocument.name : ''")
    if not name:
        return "Photoshop'da ochiq hujjat yo'q"
    path = outbox.new_path(Path(name).stem, format)
    options = {"png": "new PNGSaveOptions()", "psd": "new PhotoshopSaveOptions()",
               "jpg": "(function(){var o = new JPEGSaveOptions(); o.quality = 11; return o;})()"}[format]
    _jsx(f"app.activeDocument.saveAs(new File({_js_path(path)}), {options}, true, Extension.LOWERCASE);")
    if not path.exists():
        raise RuntimeError("Photoshop fayl saqlamadi")
    outbox.register(path)
    return f"Eksport qilindi: {path.name}"


@skill(
    description="Photoshop'da ixtiyoriy ExtendScript (JavaScript) kodini bajaradi - boshqa vositalar yetmaganda "
                "murakkab ishlar uchun (filtrlar, qatlamlar, o'lcham, effektlar). Oxirgi ifoda natijasi qaytadi.",
    params={"code": {"type": "string", "description": "Photoshop ExtendScript kodi"}},
    dangerous=True,
)
def photoshop_script(code: str) -> str:
    return _jsx(code) or "Bajarildi"
