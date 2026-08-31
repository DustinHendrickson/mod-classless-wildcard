@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"

if not defined PYTHON (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo.
    echo   Python 3 is required and was not found on this PC.
    echo.
    echo   Get it from https://www.python.org/downloads/
    echo   On the first screen, tick "Add python.exe to PATH", then run this again.
    echo.
    pause
    exit /b 1
)

%PYTHON% install.py %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
