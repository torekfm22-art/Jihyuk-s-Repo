@echo off
chcp 65001 >nul
cd /d "%~dp0"
for %%F in (SPC_*.exe) do (
    start "" "%%~fF"
    exit /b 0
)
echo [오류] SPC 실행 파일(SPC_*.exe)을 찾을 수 없습니다.
pause
exit /b 1
