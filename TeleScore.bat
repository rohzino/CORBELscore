@echo off
rem ---------------------------------------------------------------------------
rem  TeleScore launcher for Windows
rem
rem    TeleScore.bat              run TeleScore (sets itself up the first time)
rem    TeleScore.bat game.tsproj  run and open a project (or drag one onto this file)
rem    TeleScore.bat debug        run with a console window that shows errors
rem    TeleScore.bat test         run the test suite
rem    TeleScore.bat build        build dist\TeleScore\TeleScore.exe
rem    TeleScore.bat update       reinstall the requirements
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
title TeleScore

rem ---- find Python 3.10 or newer ---------------------------------------------
set "PY="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo  TeleScore needs Python 3.10 or newer.
    echo  Install it from https://www.python.org/downloads/ and tick
    echo  "Add python.exe to PATH" on the first screen, then run this again.
    echo.
    pause
    exit /b 1
)

rem ---- private environment in .venv (first run only) -------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Setting up TeleScore for the first time. This takes a minute...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail_venv
)
set "VPY=.venv\Scripts\python.exe"
set "VPYW=.venv\Scripts\pythonw.exe"

rem ---- install requirements when requirements.txt has changed ----------------
if /i "%~1"=="update" del ".venv\requirements.stamp" >nul 2>&1
fc /b "requirements.txt" ".venv\requirements.stamp" >nul 2>&1
if errorlevel 1 (
    echo Installing PyQt6 and the other requirements...
    "%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip
    "%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :fail_pip
    copy /y "requirements.txt" ".venv\requirements.stamp" >nul
)
if /i "%~1"=="update" (
    echo Requirements are up to date.
    pause
    exit /b 0
)

if /i "%~1"=="test" goto :test
if /i "%~1"=="build" goto :build
if /i "%~1"=="debug" goto :debug

rem ---- run (no console window); any arguments are project files to open ------
start "" "%VPYW%" -m telescore %*
exit /b 0

:debug
echo Running TeleScore with this console open. Errors appear here.
"%VPY%" -m telescore
echo.
echo TeleScore closed with code %errorlevel%.
pause
exit /b 0

:test
echo Installing test tools...
"%VPY%" -m pip install --disable-pip-version-check -q lxml
set "TELESCORE_SHOTS=%~dp0test-screenshots"
"%VPY%" -m unittest discover -s tests -v
if errorlevel 1 (
    echo.
    echo  Some tests failed. Copy the messages above to Claude.
) else (
    echo.
    echo  All tests passed. Screenshots of every tab are in:
    echo  %TELESCORE_SHOTS%
)
pause
exit /b 0

:build
echo Installing PyInstaller...
"%VPY%" -m pip install --disable-pip-version-check -q pyinstaller
if errorlevel 1 goto :fail_pip
"%VPY%" -m PyInstaller --noconfirm TeleScore.spec
if errorlevel 1 (
    echo.
    echo  The build failed. Copy the messages above to Claude.
    pause
    exit /b 1
)
echo.
echo  Built dist\TeleScore\TeleScore.exe
echo  Copy the whole dist\TeleScore folder to use it on another PC.
explorer "dist\TeleScore"
pause
exit /b 0

:fail_venv
echo.
echo  Could not create the .venv folder. Check that this folder is not read-only
echo  (for example inside a zip file: unzip it first).
pause
exit /b 1

:fail_pip
echo.
echo  Installing requirements failed. Check the internet connection and run
echo  "TeleScore.bat update" to try again.
pause
exit /b 1
