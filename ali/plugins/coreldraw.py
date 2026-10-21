"""CorelDRAW plagini: CorelDRAW'ni COM orqali boshqaradi (vektor dizayn, fayl ochish, eksport).
CorelDRAW kerak bo'lganda avtomatik ochiladi."""
from pathlib import Path

from .. import outbox
from ..config import config
from ..skills import skill
from . import Plugin
from ._desktop import find_progid, hex_rgb, ps_str, run_ps

_progid: str | None = None
# CorelDRAW konstantalari: cdrMillimeter, cdrPNG, cdrJPEG, cdrRGBColorImage
MM, PNG, JPEG, RGB_IMAGE = 3, 802, 774, 4


def _start() -> tuple[bool, str]:
    global _progid
    _progid = find_progid("CorelDRAW.Application")
    if not _progid:
        return False, "CorelDRAW bu kompyuterda topilmadi"
    return True, "Tayyor (kerak bo'lganda ochiladi)"


PLUGIN = Plugin(key="coreldraw", name="CorelDRAW", icon="Cd", start=_start,
                description="CorelDRAW: vektor dizayn, logotip, vizitka, banner, fayl ochish va eksport")


def _app() -> str:
    if not _progid:
        raise RuntimeError("CorelDRAW topilmadi")
    return f"$app = New-Object -ComObject {_progid}\n$app.Visible = $true\n"


def _fill(var: str, color) -> str:
    r, g, b = hex_rgb(color)
    return f"{var}.Fill.UniformColor.RGBAssign({r}, {g}, {b})\n"


def _save(doc: str, path: Path, format: str) -> str:
    if format == "pdf":
        return f"{doc}.PublishToPDF({ps_str(path)})\n"
    if format == "cdr":
        return f"{doc}.SaveAs({ps_str(path)})\n"
    filt = PNG if format == "png" else JPEG
    return (f"$f = {doc}.ExportBitmap({ps_str(path)}, {filt}, [Type]::Missing, {RGB_IMAGE}, 0, 0, 300, 300)\n"
            "$f.Finish()\n")


@skill(
    description="CorelDRAW'da yangi vektor dizayn (vizitka, banner, logotip qoralamasi) yaratadi: fon, to'rtburchaklar "
                "va matnlar. CDR (tahrirlash uchun) va tanlangan formatdagi fayl foydalanuvchiga yuboriladi.",
    params={
        "title": {"type": "string", "description": "Dizayn nomi"},
        "width_mm": {"type": "number", "description": "Kenglik, mm (vizitka 90, A4 210)"},
        "height_mm": {"type": "number", "description": "Balandlik, mm (vizitka 50, A4 297)"},
        "background": {"type": "string", "description": "Fon rangi, hex"},
        "shapes": {"type": "array", "items": {"type": "object"},
                   "description": "To'rtburchaklar: [{x, y, w, h, color}] - mm, chap yuqori burchakdan"},
        "texts": {"type": "array", "items": {"type": "object"},
                  "description": "Matnlar: [{text, x, y, size, color, font}] - x,y mm chap yuqoridan (y - asos chizig'i), size pt"},
        "format": {"type": "string", "enum": ["png", "jpg", "pdf"], "description": "Qo'shimcha eksport formati"},
    },
    required=["title", "width_mm", "height_mm"],
)
def corel_design(title: str, width_mm: float, height_mm: float, background: str = "#FFFFFF",
                 shapes: list | None = None, texts: list | None = None, format: str = "png") -> str:
    w, h = max(5.0, min(float(width_mm), 5000.0)), max(5.0, min(float(height_mm), 5000.0))
    cdr = outbox.new_path(title, "cdr")
    extra = cdr.with_suffix(f".{format}")
    s = _app() + (
        "$doc = $app.CreateDocument()\n"
        f"$doc.Unit = {MM}\n"
        f"$doc.ActivePage.SetSize({w}, {h})\n"
        "$layer = $doc.ActiveLayer\n"
        f"$bg = $layer.CreateRectangle2(0, 0, {w}, {h})\n" + _fill("$bg", background) + "$bg.Outline.SetNoOutline()\n"
    )
    for item in shapes or []:
        if not isinstance(item, dict):
            continue
        x, y = float(item.get("x", 0)), float(item.get("y", 0))
        sw, sh = max(0.1, float(item.get("w", 10))), max(0.1, float(item.get("h", 10)))
        s += f"$r = $layer.CreateRectangle2({x}, {h - y - sh}, {sw}, {sh})\n" + _fill("$r", item.get("color")) \
            + "$r.Outline.SetNoOutline()\n"
    for item in texts or []:
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        x, y = float(item.get("x", w * 0.1)), float(item.get("y", h * 0.5))
        s += (f"$t = $layer.CreateArtisticText({x}, {h - y}, {ps_str(str(item['text'])[:2000])})\n"
              f"$t.Text.Story.Size = {max(2.0, min(float(item.get('size', 24)), 1000.0))}\n")
        if item.get("font"):
            s += f"$t.Text.Story.Font = {ps_str(str(item['font'])[:80])}\n"
        s += _fill("$t", item.get("color"))
    s += _save("$doc", cdr, "cdr") + _save("$doc", extra, format)
    run_ps(s, timeout=300)
    made = [p for p in (cdr, extra) if p.exists()]
    if not made:
        raise RuntimeError("CorelDRAW fayl saqlamadi")
    for p in made:
        outbox.register(p)
    return f"Dizayn tayyor ({w:g}x{h:g} mm): " + ", ".join(p.name for p in made)


@skill(
    description="Kompyuterdagi CDR, AI, SVG, PDF yoki rasm faylni CorelDRAW'da ochadi.",
    params={"path": {"type": "string", "description": "Faylning to'liq yo'li"}},
)
def corel_open(path: str) -> str:
    file = Path(path).expanduser()
    if not file.is_file():
        return f"Fayl topilmadi: {path}"
    run_ps(_app() + f"$null = $app.OpenDocument({ps_str(file)})")
    return f"CorelDRAW'da ochildi: {file.name}"


@skill(
    description="CorelDRAW'dagi ochiq (faol) hujjatni faylga eksport qiladi va foydalanuvchiga yuboradi.",
    params={"format": {"type": "string", "enum": ["png", "jpg", "pdf", "cdr"], "description": "Fayl turi"}},
)
def corel_export(format: str = "png") -> str:
    name = run_ps(_app() + "if ($app.ActiveDocument) { Write-Output $app.ActiveDocument.Name }")
    if not name:
        return "CorelDRAW'da ochiq hujjat yo'q"
    path = outbox.new_path(Path(name).stem, format)
    run_ps(_app() + _save("$app.ActiveDocument", path, format), timeout=300)
    if not path.exists():
        raise RuntimeError("CorelDRAW fayl saqlamadi")
    outbox.register(path)
    return f"Eksport qilindi: {path.name}"
