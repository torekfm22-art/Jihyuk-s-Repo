@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python -m streamlit run app.py --server.headless true
