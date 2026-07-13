@echo off
setlocal

cd /d "%~dp0"

echo [+] Checking Python version...

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3
        goto python_ok
    )
)

python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto python_ok
)

echo [Error] Python 3.10+ is required or not found in PATH.
pause
exit /b 1

:python_ok
if not exist ".venv" (
    echo [+] Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
)

echo [+] Activating venv and installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

echo [+] Starting bot...
python dota_safe_bot.py %*

echo.
pause
