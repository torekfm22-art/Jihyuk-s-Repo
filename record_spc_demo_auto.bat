@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   SPC 프로그램 - 자동 데모 녹화
echo   실행: run_spc_desktop.bat (공정 안정성 점검)
echo ============================================================
echo.
echo   1. 샘플 데이터 준비
echo   2. run_spc_desktop.bat 으로 데스크톱 앱 실행
echo   3. 약 120초간 창 녹화 후 MP4 저장
echo.
echo   녹화 중: data\input\mes_data.xlsx 업로드 후 단계별 시연
echo   저장 위치: data\output\recordings\
echo ============================================================
echo.

python scripts\spc_demo_recording.py
if errorlevel 1 (
    echo [오류] 녹화 실패
    pause
    exit /b 1
)

explorer "data\output\recordings" 2>nul
pause
