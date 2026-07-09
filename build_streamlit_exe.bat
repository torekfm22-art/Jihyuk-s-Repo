@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  SPC 공정 안정성 점검 — Desktop EXE 빌드
echo  (Streamlit UI + 내장 앱 창)
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    pause
    exit /b 1
)

echo [1/3] 의존성 설치...
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)

echo.
echo 실행 중인 SPC Streamlit 앱 종료...
taskkill /F /IM "SPC_공정안정성점검.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo [2/3] PyInstaller 빌드 (Streamlit 번들 — 5~15분 소요)...
python -m PyInstaller spc_streamlit_app.spec --noconfirm --clean
if errorlevel 1 (
    echo [오류] 빌드 실패
    pause
    exit /b 1
)

echo.
echo [3/3] 배포용 폴더 준비...
set "DIST=dist\SPC_공정안정성점검"
if not exist "%DIST%\data\input" mkdir "%DIST%\data\input"
if not exist "%DIST%\data\output" mkdir "%DIST%\data\output"
if not exist "%DIST%\data\output\charts" mkdir "%DIST%\data\output\charts"
if not exist "%DIST%\config" mkdir "%DIST%\config"
copy /Y "config\spc_policy.yaml" "%DIST%\config\spc_policy.yaml" >nul 2>&1
copy /Y "deploy\RUN_SPC_공정안정성점검.bat" "%DIST%\RUN_SPC_공정안정성점검.bat" >nul 2>&1
copy /Y "deploy\공정안정성_배포안내.txt" "%DIST%\공정안정성_배포안내.txt" >nul 2>&1

echo.
echo ========================================
echo  빌드 완료!
echo  실행: %DIST%\SPC_공정안정성점검.exe
echo  또는: %DIST%\RUN_SPC_공정안정성점검.bat
echo.
echo  ※ 타 PC: 폴더 전체 복사 (Python 불필요)
echo  ※ WebView2(Edge) 런타임 권장 (Win10/11 기본 포함)
echo ========================================
if /i "%~1"=="nopause" exit /b 0
pause
