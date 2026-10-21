"""3ds Max plagini: design_floor_plan yaratgan 3D modelni (.obj) 3ds Max'da ochadi, MAXScript bajaradi va
fonda (3dsmaxbatch) render qiladi. 3ds Max COM'ga ega emas - dastur buyruq qatori va MAXScript orqali boshqariladi."""
import subprocess
import tempfile
from pathlib import Path

from .. import outbox
from ..skills import skill
from . import Plugin

_exe: Path | None = None


def _find() -> Path | None:
    """Eng yangi o'rnatilgan 3ds Max (C:\\Program Files\\Autodesk\\3ds Max 20xx\\3dsmax.exe)."""
    found = []
    for base in (Path(r"C:\Program Files\Autodesk"), Path(r"D:\Program Files\Autodesk")):
        if base.is_dir():
            found += [p / "3dsmax.exe" for p in base.glob("3ds Max*") if (p / "3dsmax.exe").is_file()]
    return max(found, key=lambda p: p.parent.name, default=None)


def _start() -> tuple[bool, str]:
    global _exe
    _exe = _find()
    if not _exe:
        return False, "3ds Max bu kompyuterda topilmadi"
    return True, f"Tayyor: {_exe.parent.name} (kerak bo'lganda ochiladi)"


PLUGIN = Plugin(key="max3ds", name="3ds Max", icon="3D", start=_start,
                description="Autodesk 3ds Max: 3D modelni (.obj/.fbx/.max) ochish, MAXScript, fonda render")


def _ms_str(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _script_file(code: str) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".ms", delete=False, encoding="utf-8-sig") as f:
        f.write(code)
        return Path(f.name)


def _model(path: str) -> Path:
    file = Path(path).expanduser()
    if not file.is_file() and (found := outbox.resolve(Path(path).name)):
        file = found
    if not file.is_file():
        raise RuntimeError(f"Fayl topilmadi: {path}")
    return file


def _load(file: Path) -> str:
    if file.suffix.lower() == ".max":
        return f"loadMaxFile {_ms_str(file)} quiet:true\n"
    return f"resetMaxFile #noPrompt\nimportFile {_ms_str(file)} #noPrompt\n"


@skill(
    description="3D modelni (.obj - design_floor_plan beradi, .fbx, .3ds yoki .max) 3ds Max'da ochadi: dastur "
                "ishga tushadi, model import qilinadi va ko'rinishga moslanadi. Keyin foydalanuvchi material va render qiladi.",
    params={"path": {"type": "string", "description": "Model faylining to'liq yo'li yoki outbox fayl nomi"}},
)
def max_open_model(path: str) -> str:
    if not _exe:
        return "3ds Max topilmadi"
    file = _model(path)
    script = _script_file(_load(file) + "max zoomext sel all\n")
    subprocess.Popen([str(_exe), "-U", "MAXScript", str(script)], close_fds=True)
    return f"3ds Max ochilmoqda, model import qilinadi: {file.name}"


@skill(
    description="3D modelni 3ds Max'da fonda (oynasiz, 3dsmaxbatch) render qiladi: avtomatik kamera (perspektiva, "
                "yuqoridan 3/4) va quyosh yorug'ligi bilan PNG. Natija foydalanuvchiga yuboriladi.",
    params={
        "path": {"type": "string", "description": "Model fayli (.obj/.fbx/.max)"},
        "width": {"type": "integer", "description": "Render eni, piksel (standart 1600)"},
        "height": {"type": "integer", "description": "Render bo'yi, piksel (standart 1000)"},
    },
    required=["path"],
)
def max_render(path: str, width: int = 1600, height: int = 1000) -> str:
    if not _exe:
        return "3ds Max topilmadi"
    batch = _exe.parent / "3dsmaxbatch.exe"
    if not batch.is_file():
        return "3dsmaxbatch.exe topilmadi (3ds Max 2018+ kerak)"
    file = _model(path)
    out = outbox.new_path(f"{file.stem} render", "png")
    w, h = max(320, min(int(width), 6000)), max(240, min(int(height), 6000))
    script = _script_file(_load(file) + f"""
local bb = #(objects.min, objects.max)
local c = (bb[1] + bb[2]) / 2
local size = distance bb[1] bb[2]
local cam = Targetcamera fov:45 target:(Targetobject pos:c)
cam.pos = c + [size * 0.55, -size * 0.75, size * 0.65]
Daylight pos:(c + [0, 0, size]) target:(Targetobject pos:c)
render camera:cam outputwidth:{w} outputheight:{h} outputfile:{_ms_str(out)} vfb:false
""")
    try:
        proc = subprocess.run([str(batch), str(script)], capture_output=True, text=True, errors="replace", timeout=900)
    finally:
        script.unlink(missing_ok=True)
    if not out.exists():
        raise RuntimeError("Render bo'lmadi: " + (proc.stdout + proc.stderr).strip()[-800:])
    outbox.register(out)
    return f"Render tayyor: {out.name}"


@skill(
    description="3ds Max'da ixtiyoriy MAXScript kodini fonda (3dsmaxbatch) bajaradi va chiqishini qaytaradi - "
                "modelga material, yorug'lik, eksport kabi murakkab ishlar uchun.",
    params={"code": {"type": "string", "description": "MAXScript kodi"}},
    dangerous=True,
)
def max_script(code: str) -> str:
    if not _exe:
        return "3ds Max topilmadi"
    batch = _exe.parent / "3dsmaxbatch.exe"
    script = _script_file(code)
    try:
        proc = subprocess.run([str(batch), str(script)], capture_output=True, text=True, errors="replace", timeout=900)
    finally:
        script.unlink(missing_ok=True)
    return (proc.stdout + proc.stderr).strip()[-3000:] or "Bajarildi"
