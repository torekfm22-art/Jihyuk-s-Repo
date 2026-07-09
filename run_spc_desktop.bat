@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SPC 공정 안정성 점검 — 데스크톱 앱 (개발 모드)
python src/spc_streamlit/desktop_launcher.py
if /i not "%~1"=="nopause" pause
