@echo off
setlocal enableextensions
cd /d "%~dp0"

rem Find a working Python 3. Each candidate is TESTED by actually running it,
rem not just by whether the command exists -- on Windows "python" is often a
rem Microsoft Store stub or a .bat shim, and the "py" launcher is frequently
rem left pointing at a Python that was moved or uninstalled. We use "call" so a
rem .bat shim (e.g. python.bat -> python3) returns control here instead of
rem ending this script. python3 is tried first because it is the least likely
rem to be a stub, py is tried last because it is the most likely to be broken.
set "PYTHON="
for %%C in (python3 python "py -3") do (
    if not defined PYTHON (
        call %%~C -c "import sys; sys.exit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON=%%~C"
    )
)

if not defined PYTHON (
    echo.
    echo   Could not find a working Python 3 on this PC.
    echo.
    echo   Install it from https://www.python.org/downloads/
    echo   On the first screen of the installer, tick "Add python.exe to PATH",
    echo   then close this window and run install.bat again.
    echo.
    echo   ^(If you think Python is already installed, it may be a broken "py"
    echo    launcher or a Microsoft Store stub. Reinstalling from python.org
    echo    with "Add to PATH" ticked fixes it.^)
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo.
call %PYTHON% install.py %*
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" (
    echo Installer exited with an error ^(code %RESULT%^). Nothing above says
    echo "Done"? Read the message and re-run, or ask on the realm's Discord.
)
pause
exit /b %RESULT%
