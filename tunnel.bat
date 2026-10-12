@echo off
chcp 65001 >nul
rem Telefondan istalgan joydan (Wi-Fi shart emas) HTTPS orqali kirish uchun.
rem Avval start.bat ishga tushgan bo'lishi kerak.
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo cloudflared o'rnatilmoqda...
  winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
  echo.
  echo O'rnatildi. Bu oynani yopib, tunnel.bat ni qayta ishga tushiring.
  pause
  exit /b
)
echo.
echo Pastda chiqadigan https://....trycloudflare.com havolasini telefonda oching.
echo (Har ishga tushirishda havola o'zgaradi. Doimiy manzil uchun README ga qarang.)
echo.
cloudflared tunnel --url http://localhost:8000
pause
