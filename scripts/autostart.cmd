@echo off
rem Ali - kompyuter yoqilganda yashirin ishga tushadi (Startup papkasidagi Ali.vbs chaqiradi).
rem Qulab tushsa yoki o'zini kuchaytirib qayta ishga tushsa - 10 soniyadan keyin qayta yoqiladi.
rem Boshqa Ali allaqachon ishlayotgan bo'lsa (port band) - jim chiqadi.
chcp 65001 >nul
cd /d "%~dp0.."
set ALI_SUPERVISED=1
set PYTHONUTF8=1
:loop
python -X utf8 server.py >> logs\autostart.log 2>&1
if %errorlevel%==0 goto :eof
timeout /t 10 /nobreak >nul
goto loop
