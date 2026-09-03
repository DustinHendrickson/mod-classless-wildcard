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

rem The install paints icons, which needs the Pillow library. Install it here
rem so the player sees it happen, rather than deep inside the installer.
call %PYTHON% -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo The Python library Pillow is needed to paint the Hero and elemental icons.
    echo Installing it now...
    call %PYTHON% -m pip install --user pillow
    call %PYTHON% -c "import PIL" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   Pillow could not be installed. Run this, then run install.bat again:
        echo     %PYTHON% -m pip install --user pillow
        echo.
        pause
        exit /b 1
    )
    echo.
)
echo This installs the full Hero client: the Hero name, the single-class
echo creation screen, the Hero text, armored outfit and emblem, the elemental
echo ability variants and the addon. It patches Wow.exe to accept the custom
echo interface, backing it up first. CLOSE WORLD OF WARCRAFT before continuing.
echo.

rem ---------------------------------------------------------------------------
rem Which World of Warcraft folder to patch.
rem
rem install_path.txt sits beside this script and remembers the answer, so the
rem folder is typed once per PC. It is not shipped: the first run that has to
rem ask creates it, and a player can write the path in by hand instead. Lines
rem starting with # are ignored. A folder given on install.bat's command line
rem wins and is not written down.
rem
rem The reads below all happen at label level, never inside a parenthesised
rem block, so plain %VAR% expansion is re-evaluated each pass and delayed
rem expansion is not needed -- which also keeps a folder name containing "!"
rem intact.
rem ---------------------------------------------------------------------------
set "PATHFILE=%~dp0install_path.txt"

rem Did the caller already name a folder? Anything that is not a switch counts.
rem "shift" does not touch %*, so the original arguments still pass through.
set "CALLERPATH="
:cwScanArgs
if "%~1"=="" goto cwScanned
set "CWARG=%~1"
if not "%CWARG:~0,1%"=="-" set "CALLERPATH=1"
shift
goto cwScanArgs
:cwScanned

set "WOWPATH="
if defined CALLERPATH goto cwRun
if not exist "%PATHFILE%" goto cwAsk
for /f "usebackq eol=# delims=" %%L in ("%PATHFILE%") do if not defined WOWPATH set "WOWPATH=%%~L"
if not defined WOWPATH goto cwAsk
call :cwCleanPath
if exist "%WOWPATH%\Data" goto cwUseSaved
echo   install_path.txt names a folder with no Data folder in it:
echo     %WOWPATH%
echo   Asking again. Edit or delete install_path.txt to change it.
echo.
set "WOWPATH="

:cwAsk
echo Where is your World of Warcraft 3.3.5a folder?
echo It is the folder that holds Wow.exe and the Data folder.
echo Leave it blank to let the installer search the usual places itself.
echo.
set "WOWPATH="
set /p "WOWPATH=WoW folder: "
echo.
if not defined WOWPATH goto cwRun
call :cwCleanPath
if not exist "%WOWPATH%\Data" goto cwBadPath
> "%PATHFILE%" echo # The World of Warcraft folder install.bat patches.
>>"%PATHFILE%" echo # Delete this file, or clear the line below, to be asked again.
>>"%PATHFILE%" echo %WOWPATH%
echo Remembered in install_path.txt.
echo.
goto cwRun

:cwBadPath
echo   There is no Data folder in:
echo     %WOWPATH%
echo   That is not a WoW install folder.
echo.
goto cwAsk

:cwUseSaved
echo Using the folder from install_path.txt:
echo   %WOWPATH%
echo.

:cwRun
set "PATHARG="
if not defined CALLERPATH if defined WOWPATH set PATHARG="%WOWPATH%"

call %PYTHON% install.py %PATHARG% %*
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" (
    echo Installer exited with an error ^(code %RESULT%^). Nothing above says
    echo "Done"? Read the message and re-run, or ask on the realm's Discord.
)
pause
exit /b %RESULT%

rem Strip the quotes a pasted path often carries, and a trailing backslash: it
rem would escape the closing quote when the path is passed to Python.
:cwCleanPath
set WOWPATH=%WOWPATH:"=%
if "%WOWPATH:~-1%"=="\" set "WOWPATH=%WOWPATH:~0,-1%"
goto :eof
