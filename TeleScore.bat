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

rem ---- find a Python that PyQt6 has ready-made packages for -----------------
rem  PyQt6 ships for 64-bit, standard (not free-threaded) CPython 3.10 or newer.
rem  Anything else makes pip try to compile Qt from source, which fails.
set "CHECK=import sys,struct,sysconfig; sys.exit(0 if sys.version_info>=(3,10) and struct.calcsize('P')==8 and not sysconfig.get_config_var('Py_GIL_DISABLED') else 1)"
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PY="
call :try py -3
for %%V in (3.13 3.12 3.14 3.11 3.10) do if not defined PY call :try py -%%V
for %%V in (3.13 3.12 3.14 3.11 3.10) do if not defined PY call :try py -%%V-64
if not defined PY call :try python
if not defined PY goto :fail_python

rem ---- private environment in .venv -----------------------------------------
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "%CHECK%" >nul 2>&1
    if errorlevel 1 (
        echo The existing .venv uses a Python that PyQt6 does not support. Rebuilding it...
        rmdir /s /q ".venv"
    )
)
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
    "%VPY%" -m pip install --disable-pip-version-check --only-binary=PyQt6,PyQt6-Qt6,PyQt6-sip -r requirements.txt
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
rem  "if errorlevel 1" misses negative codes, which is how a crash on exit shows up.
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo  Some tests failed, or Python stopped abnormally ^(exit code %RC%^).
    echo  Copy the messages above to Claude.
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
echo  Installing requirements failed. This Python is:
"%VPY%" -c "import platform,struct; print('   ', platform.python_implementation(), platform.python_version(), struct.calcsize('P')*8, 'bit,', platform.machine())"
echo  Check the internet connection and run "TeleScore.bat update" to try again.
echo  If it fails again, copy these messages to Claude.
pause
exit /b 1

:fail_python
echo.
echo  TeleScore needs 64-bit Python 3.10 or newer (the standard build, not the
echo  free-threaded "t" build). PyQt6 has no packages for anything else.
echo.
echo  Pythons found on this PC:
py --list-paths 2>nul || python -c "import sys,struct; print('   ', sys.version, struct.calcsize('P')*8, 'bit')" 2>nul || echo     none
echo.
echo  Install "Windows installer (64-bit)" from https://www.python.org/downloads/
echo  and tick "Add python.exe to PATH" on the first screen, then run this again.
pause
exit /b 1

rem ---- try one Python command; keep it when it passes the check --------------
:try
%* -c "%CHECK%" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b 0
