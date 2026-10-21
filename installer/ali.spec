# PyInstaller: Ali.exe (bitta papka). Yig'ish: installer\build_windows.ps1
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = SPECPATH + "\\.."

hidden = (collect_submodules("ali") + collect_submodules("uvicorn") + collect_submodules("telegram")
          + ["runtime", "gateway", "firebase_admin", "google.genai", "edge_tts", "multipart"])
datas = [(root + "\\web", "web"), (root + "\\agents", "agents")]
datas += collect_data_files("certifi") + collect_data_files("edge_tts")

a = Analysis(
    [root + "\\desktop.py"],
    pathex=[root],
    hiddenimports=hidden,
    datas=datas,
    excludes=["tkinter", "pytest", "speech_recognition", "sounddevice", "pygame"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ali",
    icon=root + "\\installer\\ali.ico",
    console=True,  # oyna yopilsa Ali to'xtaydi - foydalanuvchi uchun aniq
)
coll = COLLECT(exe, a.binaries, a.datas, name="Ali")
