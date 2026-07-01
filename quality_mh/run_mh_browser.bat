@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 품질 표준인원 산출 시스템 (브라우저 모드)...
python -m streamlit run app.py --server.headless false
pause
