@echo off
:: Change directory to the folder where this batch file is located
cd /d "%~dp0"

:: 1. Create the virtual environment if it doesn't exist
if not exist ".venv" (
    echo [.venv not found] Creating virtual environment...
    python -m venv .venv
)

:: 2. Check and install packages from requirements.txt (Fast skip if already installed)
if exist "requirements.txt" (
    echo Checking packages from requirements.txt...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
    echo [Warning] requirements.txt not found! Skipping package check.
)

:: 3. Always run the main application
echo ---------------------------------------
echo Running main.py...
.venv\Scripts\python.exe main.py

:: Keep the window open in case of errors
pause