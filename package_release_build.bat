@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 빌드 후 배포 ZIP까지 한 번에 진행합니다...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_release.ps1" -Build
if errorlevel 1 (
    pause
    exit /b 1
)
explorer "%~dp0release"
pause
