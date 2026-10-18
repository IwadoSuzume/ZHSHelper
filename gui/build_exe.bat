@echo off
REM Developer-only: builds the release - dist\ZHSHelper\ plus
REM installer\output\ZHSHelper-Setup.exe - via gui\build_release.py.
REM End users never run this; they install with ZHSHelper-Setup.exe.
REM First time only: venv\Scripts\pip install -r requirements-build.txt
setlocal
cd /d %~dp0\..
venv\Scripts\python.exe gui\build_release.py --installer %*
if errorlevel 1 (
  echo.
  echo Build FAILED.
  exit /b 1
)
echo.
echo Build complete: installer\output\ZHSHelper-Setup.exe
