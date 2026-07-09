@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SPC 공정 안정성 점검 (Streamlit) 시작...
python -m streamlit run src/spc_streamlit/app.py --server.headless true
pause
