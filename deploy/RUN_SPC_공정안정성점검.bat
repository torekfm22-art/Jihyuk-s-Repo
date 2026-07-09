@echo off
chcp 65001 >nul
cd /d "%~dp0"
for %%F in (SPC_공정안정성점검.exe) do (
    start "" "%%~fF"
    exit /b 0
)
echo [오류] SPC_공정안정성점검.exe 를 찾을 수 없습니다.
pause
exit /b 1
