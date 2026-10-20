@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Ali - TO'LIQ RUXSAT rejimi (faqat o'z kompyuteringiz uchun): barcha vositalar tasdiqsiz ishlaydi.
rem Administrator huquqi kerak bo'lsa: faylni o'ng tugma -> "Run as administrator".
set FULL_ACCESS=true
echo Kutubxonalar tekshirilmoqda...
python -m pip install -q -r requirements.txt
start "" http://localhost:8000
python server.py
pause
