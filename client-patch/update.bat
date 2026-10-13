@echo off
setlocal enableextensions
cd /d "%~dp0"

rem update.py cannot rewrite this file while cmd is reading it, so a newer
rem copy is left beside it as update.bat.new. Swap it in and start over.
if exist "%~dp0update.bat.new" (
    move /y "%~dp0update.bat.new" "%~dp0update.bat" >nul
    call "%~dp0update.bat" %*
    exit /b
)

rem Find a working Python 3, the same way install.bat does: each candidate is
rem tested by running it, since "python" is often a Store stub and "py" can
rem point at a Python that was removed.
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
    echo   then close this window and run update.bat again.
    echo.
    pause
    exit /b 1
)

echo Using Python: %PYTHON%
echo.
echo This fetches the latest client patch and addon from GitHub and replaces
echo the copies in this folder and in client-addon. Run install.bat afterwards.
echo.

call %PYTHON% update.py %*
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" (
    echo The update did not finish ^(code %RESULT%^). Read the message above
    echo and run update.bat again.
)
pause
exit /b %RESULT%
