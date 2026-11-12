@echo off
setlocal
cd /d "%~dp0"

set "LOG=build.log"
echo ==== ZHSHelper build ==== > "%LOG%"
echo started: %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"

venv\Scripts\python.exe gui\build_release.py %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo. >> "%LOG%"
echo ==== exit code: %RC% ==== >> "%LOG%"

type "%LOG%"
echo.
if not "%RC%"=="0" (
    echo BUILD FAILED - full output above and in build.log
    pause
    exit /b %RC%
)

echo Build OK: dist\ZHSHelper\ZHSHelper.exe
echo Optional installer: run this file with --installer (needs Inno Setup 6).
echo.
pause
