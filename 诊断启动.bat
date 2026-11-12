@echo off
cd /d "%~dp0"
echo ==== python ====
venv\Scripts\python.exe -V
echo.
echo ==== webview / clr ====
venv\Scripts\python.exe -c "import webview;print('pywebview', getattr(webview, '__version__', '?'))"
venv\Scripts\python.exe -c "import clr;print('pythonnet clr OK')"
echo.
echo ==== launch GUI (console) ====
venv\Scripts\python.exe "launch_gui.py"
echo ==== exit code: %ERRORLEVEL% ====
if exist "startup_error.log" (
    echo.
    echo ---- startup_error.log ----
    type "startup_error.log"
)
echo.
pause
