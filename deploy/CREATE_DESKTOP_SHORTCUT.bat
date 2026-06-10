@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "EXE="
for %%F in (SPC_*.exe) do set "EXE=%%~fF"
if not defined EXE (
    echo [오류] SPC_*.exe 를 찾을 수 없습니다.
    pause
    exit /b 1
)
set "LNK=%USERPROFILE%\Desktop\SPC 공정능력 분석.lnk"

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');" ^
  "$s.TargetPath = '%EXE%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.Description = 'SPC 공정능력 분석';" ^
  "$s.Save()"

if exist "%LNK%" (
    echo 바탕화면에 바로가기를 만들었습니다.
) else (
    echo 바로가기 생성에 실패했습니다. RUN_SPC.bat 을 사용하세요.
)
pause
