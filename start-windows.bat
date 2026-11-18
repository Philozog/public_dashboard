@echo off
rem Double-click to install (first time only) and start AP Terminal.
setlocal
cd /d "%~dp0"
title AP Terminal

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo Python is not installed. Trying to install it with winget...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo If Python installed, close this window and double-click start-windows.bat again.
    echo Otherwise install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" on the first screen.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo First run: setting up. This takes a few minutes, only once.
    %PY% -m venv .venv || goto :failed
)

rem Reinstall packages only when requirements.txt has changed.
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto :failed
    copy /y requirements.txt ".venv\installed-requirements.txt" >nul
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Something went wrong. See the message above, or the Troubleshooting
echo section of README.md.
pause
exit /b 1
