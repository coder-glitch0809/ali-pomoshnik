"""AutoCAD plagini: AutoCAD'ni COM orqali boshqaradi (chizma ochish, DWG/PDF ga saqlash, buyruq bajarish).
design_floor_plan yaratgan .dxf rejani shu yerda ochib davom ettirish mumkin. AutoCAD kerak bo'lganda ochiladi."""
from pathlib import Path

from .. import outbox
from ..config import config
from ..skills import skill
from . import Plugin
from ._desktop import find_progid, ps_str, run_ps

_progid: str | None = None
# AcSaveAsType: ac2018_dwg = 64, ac2018_dxf = 65 (AutoCAD 2018+ ochadi)
DWG, DXF = 64, 65


def _start() -> tuple[bool, str]:
    global _progid
    _progid = find_progid("AutoCAD.Application")
    if not _progid:
        return False, "AutoCAD bu kompyuterda topilmadi"
    if config.plugins_open_apps:
        run_ps(_app(), timeout=300)
        return True, "Ishga tushirildi"
    return True, "Tayyor (kerak bo'lganda ochiladi)"


PLUGIN = Plugin(key="autocad", name="AutoCAD", icon="Ac", start=_start,
                description="AutoCAD: reja/chizma (.dxf, .dwg) ochish, DWG va PDF ga saqlash, buyruqlar bajarish")


def _app() -> str:
    """Ochiq AutoCAD'ga ulanadi, yo'q bo'lsa ishga tushiradi."""
    if not _progid:
        raise RuntimeError("AutoCAD topilmadi")
    return (f"try {{ $app = [Runtime.InteropServices.Marshal]::GetActiveObject({ps_str(_progid)}) }}\n"
            f"catch {{ $app = New-Object -ComObject {_progid} }}\n$app.Visible = $true\n")


@skill(
    description="Chizmani (.dwg yoki .dxf - masalan design_floor_plan yaratgan reja) AutoCAD'da ochadi. "
                "save_as_dwg=true bo'lsa DWG nusxasi ham saqlanib foydalanuvchiga yuboriladi.",
    params={
        "path": {"type": "string", "description": "Faylning to'liq yo'li (.dwg/.dxf)"},
        "save_as_dwg": {"type": "boolean", "description": "DWG formatga ham saqlansinmi"},
    },
    required=["path"],
)
def autocad_open(path: str, save_as_dwg: bool = False) -> str:
    file = Path(path).expanduser()
    if not file.is_file() and (found := outbox.resolve(Path(path).name)):
        file = found
    if not file.is_file():
        return f"Fayl topilmadi: {path}"
    script = _app() + f"$doc = $app.Documents.Open({ps_str(file)})\n$doc.Activate()\n"
    dwg = None
    if save_as_dwg and file.suffix.lower() != ".dwg":
        dwg = outbox.new_path(file.stem, "dwg")
        script += f"$doc.SaveAs({ps_str(dwg)}, {DWG})\n"
    run_ps(script, timeout=300)
    if dwg and dwg.exists():
        outbox.register(dwg)
        return f"AutoCAD'da ochildi va DWG saqlandi: {dwg.name}"
    return f"AutoCAD'da ochildi: {file.name}"


@skill(
    description="AutoCAD'dagi faol chizmani PDF (Layout/Model chop etish) yoki DWG/DXF qilib saqlaydi va yuboradi.",
    params={"format": {"type": "string", "enum": ["pdf", "dwg", "dxf"], "description": "Fayl turi"}},
)
def autocad_export(format: str = "pdf") -> str:
    name = run_ps(_app() + "if ($app.Documents.Count) { $app.ActiveDocument.Name }")
    if not name:
        return "AutoCAD'da ochiq chizma yo'q"
    path = outbox.new_path(Path(name).stem, format)
    if format == "pdf":
        script = (_app() + "$doc = $app.ActiveDocument\n$doc.SetVariable('BACKGROUNDPLOT', 0)\n"
                  "$layout = $doc.ActiveLayout\n$layout.ConfigName = 'DWG To PDF.pc3'\n$layout.RefreshPlotDeviceInfo()\n"
                  f"$null = $doc.Plot.PlotToFile({ps_str(path)}, 'DWG To PDF.pc3')\n")
    else:
        script = _app() + f"$app.ActiveDocument.SaveAs({ps_str(path)}, {DWG if format == 'dwg' else DXF})\n"
    run_ps(script, timeout=300)
    if not path.exists():
        raise RuntimeError("AutoCAD fayl saqlamadi")
    outbox.register(path)
    return f"Eksport qilindi: {path.name}"


@skill(
    description="AutoCAD buyruq qatoriga buyruq yuboradi (masalan '_ZOOM _E', '_LINE 0,0 1000,0 ', LISP ifodasi). "
                "Har buyruq oxiriga Enter avtomatik qo'shiladi. Murakkab chizish uchun.",
    params={"command": {"type": "string", "description": "AutoCAD buyrug'i yoki AutoLISP ifodasi"}},
    dangerous=True,
)
def autocad_command(command: str) -> str:
    cmd = command.rstrip("\n") + "\n"
    run_ps(_app() + "if (-not $app.Documents.Count) { $null = $app.Documents.Add() }\n"
           f"$app.ActiveDocument.SendCommand({ps_str(cmd)})\n", timeout=300)
    return "Buyruq yuborildi"
