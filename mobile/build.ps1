# Telefon ilovasini yig'ish. Gradle va Dart kirill harfli yo'lda (D:\проекты\...) ishlamaydi, shuning uchun
# loyiha D:\dev\ali-mobile ga nusxalanadi va o'sha yerda yig'iladi. Natija: ..\dist\
#   powershell -ExecutionPolicy Bypass -File mobile\build.ps1 -Target full    # APK, saytdan yuklash uchun
#   powershell -ExecutionPolicy Bypass -File mobile\build.ps1 -Target store   # AAB, Play Market uchun
param([ValidateSet('full', 'store')][string]$Target = 'full', [string]$Dev = 'D:\dev')
$ErrorActionPreference = 'Stop'

$env:JAVA_HOME = "$Dev\jdk17"
$env:ANDROID_HOME = "$Dev\android-sdk"
$env:PUB_CACHE = "$Dev\pub-cache"
$env:GRADLE_USER_HOME = "$Dev\gradle"
$env:Path = "$Dev\flutter\bin;$env:JAVA_HOME\bin;$env:Path"

$src = $PSScriptRoot
$work = "$Dev\ali-mobile"
New-Item -ItemType Directory -Force $work | Out-Null
# /MIR: ish papkasi manbaning aniq nusxasi bo'ladi (yig'ish natijalari bundan mustasno)
robocopy $src $work /MIR /XD build .dart_tool .gradle /XF build.ps1 /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Nusxalashda xato' }

Set-Location $work
flutter config --android-sdk $env:ANDROID_HOME | Out-Null
flutter pub get
if ($Target -eq 'full') {
    flutter build apk --release --flavor full --dart-define=FLAVOR=full
    $out = 'build\app\outputs\flutter-apk\app-full-release.apk'
} else {
    flutter build appbundle --release --flavor store --dart-define=FLAVOR=store
    $out = 'build\app\outputs\bundle\storeRelease\app-store-release.aab'
}
if ($LASTEXITCODE -ne 0) { throw 'Yig''ish muvaffaqiyatsiz' }
$dist = Join-Path (Split-Path -Parent $src) 'dist'
New-Item -ItemType Directory -Force $dist | Out-Null
Copy-Item $out $dist -Force
Write-Host "Tayyor: $dist\$(Split-Path -Leaf $out)"
