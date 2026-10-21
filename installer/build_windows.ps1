# Ali Windows o'rnatuvchisini yig'ish: dist\Ali-Setup-1.0.0.exe
#   powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
# Kerak: Python 3.12+ va Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Toza muhit: faqat server kutubxonalari (ovoz/mikrofon kutubxonalarisiz)
if (-not (Test-Path .venv-build)) { python -m venv .venv-build }
$py = Join-Path $root '.venv-build\Scripts\python.exe'
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-server.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'pip install muvaffaqiyatsiz' }

# Belgi (ico) - Ali avataridan
if (-not (Test-Path installer\ali.ico)) {
    & $py -c "from PIL import Image; Image.open('web/assets/ali-telegram-avatar.png').convert('RGBA').save('installer/ali.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
}

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build installer\ali.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller muvaffaqiyatsiz' }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 topilmadi: winget install JRSoftware.InnoSetup' }
& $iscc installer\ali.iss
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup muvaffaqiyatsiz' }
Write-Host "Tayyor: $(Get-ChildItem dist\Ali-Setup-*.exe | Select-Object -Last 1 -ExpandProperty FullName)"
