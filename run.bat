@echo off
REM Enter the directory where the script is located
cd /d %~dp0

REM Activate virtual environment
call venv\Scripts\activate


REM Upgrade pip
python -m pip install --upgrade pip >nul 2>&1

REM Install dependencies (if requirements.txt exists)
if exist requirements.txt (
    pip install -r requirements.txt --quiet >nul 2>&1
)

REM 运行主程序
python main.py

REM 保持窗口不自动关闭，方便查看输出
echo.
pause
