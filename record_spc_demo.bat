@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   SPC 프로그램 데모 녹화 (수동)
echo   실행: run_spc_desktop.bat (공정 안정성 점검)
echo ============================================================
echo.
echo   [사전 준비] prepare_spc_demo.bat 실행 권장
echo.
echo   1. SPC 데스크톱 앱을 실행합니다
echo   2. 녹화 도구가 열리면 Enter로 시작/종료합니다
echo   3. MP4 파일은 data\output\recordings\ 에 저장됩니다
echo.
echo   [데모 순서 제안 - 약 3~4분]
echo     - data\input\mes_data.xlsx 업로드
echo     - 공정 안정성 점검 시작 클릭
echo     - 2.데이터분석 -^> 3.정규성 -^> 4.관리도 -^> 5.공정능력 -^> 6.결론
echo     - Excel/PDF 다운로드 확인
echo.
echo   [자동 녹화] record_spc_demo_auto.bat 사용
echo.
echo ============================================================
echo.

python scripts\prepare_spc_demo.py --skip-analysis --skip-deps 2>nul

python -c "import mss, cv2, numpy" 2>nul
if errorlevel 1 (
    echo [설치] 녹화 패키지 설치 중...
    pip install mss opencv-python numpy -q
    if errorlevel 1 (
        echo [오류] 패키지 설치 실패. 수동 실행:
        echo   pip install mss opencv-python numpy
        pause
        exit /b 1
    )
)

if not exist "data\output\recordings" mkdir "data\output\recordings"

echo [1/2] SPC 데스크톱 앱 실행 (run_spc_desktop.bat)...
start "SPC Desktop" cmd /c "run_spc_desktop.bat nopause"

echo       Streamlit 서버 기동 대기 (15초)...
timeout /t 15 /nobreak >nul

echo [2/2] 녹화 도구 실행...
python scripts\record_spc_screen.py --window "SPC 공정 안정성" --label "SPC 공정 안정성 점검"

echo.
echo 녹화 파일 위치: data\output\recordings\
explorer "data\output\recordings" 2>nul
pause
