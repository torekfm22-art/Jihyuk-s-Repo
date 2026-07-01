@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 품질 표준인원 산출 시스템 (데스크톱) 시작...
python desktop_launcher.py
if errorlevel 1 pause
