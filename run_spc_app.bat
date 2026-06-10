@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SPC 공정능력 분석 프로그램 시작...
python src\spc_gui.py
if errorlevel 1 pause
