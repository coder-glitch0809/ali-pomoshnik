@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "ALI_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "ALI_PYTHON=.venv\Scripts\python.exe"
"%ALI_PYTHON%" -X utf8 desktop.py --localhost %*
if errorlevel 1 pause
