@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  SPC — 타 PC 배포 ZIP 만들기
echo ========================================
echo.
echo  [1] EXE만 있으면: package_release.bat
echo  [2] 빌드+ZIP 한번에: package_release_build.bat
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_release.ps1"
if errorlevel 1 (
    echo.
    echo [오류] 패키징 실패. dist\SPC_공정능력분석 이 있는지 확인하세요.
    echo         없으면 먼저 build_exe.bat 을 실행하세요.
    pause
    exit /b 1
)

echo.
explorer "%~dp0release"
pause
