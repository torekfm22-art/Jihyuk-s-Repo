@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  SPC 공정능력 분석 — EXE 빌드
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
echo 실행 중인 SPC 프로그램 종료...
taskkill /F /IM "SPC_공정능력분석.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo [2/3] PyInstaller 빌드 (수 분 소요)...
python -m PyInstaller spc_app.spec --noconfirm --clean
if errorlevel 1 (
    echo [오류] 빌드 실패
    pause
    exit /b 1
)

echo.
echo [3/3] 배포용 폴더 준비...
set "DIST=dist\SPC_공정능력분석"
if not exist "%DIST%\data\input" mkdir "%DIST%\data\input"
if not exist "%DIST%\data\output" mkdir "%DIST%\data\output"
if not exist "%DIST%\data\output\charts" mkdir "%DIST%\data\output\charts"
copy /Y "DISTRIBUTE.txt" "%DIST%\DISTRIBUTE.txt" >nul 2>&1
copy /Y "deploy\RUN_SPC.bat" "%DIST%\RUN_SPC.bat" >nul 2>&1
copy /Y "deploy\CREATE_DESKTOP_SHORTCUT.bat" "%DIST%\CREATE_DESKTOP_SHORTCUT.bat" >nul 2>&1
copy /Y "deploy\IT_GUIDE.txt" "%DIST%\IT_GUIDE.txt" >nul 2>&1
copy /Y "deploy\배포_빠른시작.txt" "%DIST%\배포_빠른시작.txt" >nul 2>&1

echo.
echo ========================================
echo  빌드 완료!
echo  실행 파일: %DIST%\SPC_공정능력분석.exe
echo.
echo  타 PC 배포 ZIP: package_release.bat 더블클릭
echo  (또는 package_release_build.bat = 빌드+ZIP 한번에)
echo ========================================
if /i "%~1"=="nopause" exit /b 0
pause
