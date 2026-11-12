@echo off
cd /d "%~dp0"

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "launch_gui.py"
    exit /b 0
)

if exist "venv\Scripts\python.exe" (
    start "" "venv\Scripts\python.exe" "launch_gui.py"
    exit /b 0
)

echo venv python not found. Run run.bat first? 
pause
