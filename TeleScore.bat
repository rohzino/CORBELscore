@echo off
rem ---------------------------------------------------------------------------
rem  TeleScore launcher for Windows 10 / 11 (64-bit)
rem
rem    TeleScore.bat               run TeleScore (sets itself up the first time)
rem    TeleScore.bat game.tsproj   run and open a project (or drag one onto this file)
rem    TeleScore.bat test          run the test suite and a check of the app window
rem    TeleScore.bat build         make a portable copy in dist\TeleScore
rem    TeleScore.bat update        download the runtime again
rem
rem  TeleScore runs on Electron. The first run downloads it (about 160 MB) from
rem  GitHub into the runtime folder and checks its SHA-256 before using it.
rem  Nothing is installed on the computer; delete the folder to remove it.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
title TeleScore

set "EV=44.9.3"
set "ESHA=41a1ffa0541cb0f2c9b9fe920dd2cef1793ad0ea2ada1a9582958880f4d1b23c"
set "EZIP=electron-v%EV%-win32-x64.zip"
set "EURL=https://github.com/electron/electron/releases/download/v%EV%/%EZIP%"
set "RT=%~dp0runtime"

if /i "%~1"=="update" if exist "%RT%" rmdir /s /q "%RT%"
if not exist "%RT%\electron.exe" call :setup || goto :fail
if not exist "%RT%\version" goto :fail
set /p HAVE=<"%RT%\version"
if not "%HAVE%"=="%EV%" (
    echo The runtime is %HAVE%, TeleScore wants %EV%. Downloading the right one...
    rmdir /s /q "%RT%"
    call :setup || goto :fail
)

if /i "%~1"=="test"   goto :test
if /i "%~1"=="build"  goto :build
if /i "%~1"=="update" shift

start "" "%RT%\electron.exe" . %1 %2
exit /b 0

rem ---- first-run setup -------------------------------------------------------
:setup
echo Setting up TeleScore for the first time.
echo Downloading Electron %EV% from GitHub (about 160 MB)...
if not exist "%RT%" mkdir "%RT%"
set "ZIP=%TEMP%\%EZIP%"
if exist "%ZIP%" del "%ZIP%"
where curl.exe >nul 2>&1
if not errorlevel 1 (
    curl.exe -L --fail --progress-bar -o "%ZIP%" "%EURL%"
) else (
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%EURL%' -OutFile '%ZIP%'"
)
if not exist "%ZIP%" (
    echo.
    echo Could not download %EURL%
    echo Check the internet connection, or download that file yourself, put it in
    echo %TEMP% and run TeleScore.bat again.
    exit /b 1
)
echo Checking the download...
set "GOT="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%ZIP%" SHA256') do if not defined GOT set "GOT=%%H"
set "GOT=%GOT: =%"
if /i not "%GOT%"=="%ESHA%" (
    echo.
    echo The download does not match the expected SHA-256 and was not used.
    echo   expected %ESHA%
    echo   got      %GOT%
    del "%ZIP%"
    exit /b 1
)
echo Unpacking...
tar -xf "%ZIP%" -C "%RT%" 2>nul
if not exist "%RT%\electron.exe" powershell -NoProfile -Command "Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%RT%'"
del "%ZIP%"
if not exist "%RT%\electron.exe" (
    echo Could not unpack the runtime.
    exit /b 1
)
echo Ready.
exit /b 0

rem ---- tests -----------------------------------------------------------------
:test
echo Running the test suite...
set "ELECTRON_RUN_AS_NODE=1"
"%RT%\electron.exe" --test
set "UNIT=%errorlevel%"
set "ELECTRON_RUN_AS_NODE="
echo.
echo Checking the app window, pictures and shortcuts...
set "TELESCORE_SMOKE=%TEMP%\telescore-check"
if exist "%TELESCORE_SMOKE%" rmdir /s /q "%TELESCORE_SMOKE%"
"%RT%\electron.exe" .
set "SMOKE=%errorlevel%"
if exist "%TELESCORE_SMOKE%\report.txt" type "%TELESCORE_SMOKE%\report.txt"
echo Pictures from the check are in %TELESCORE_SMOKE%
echo.
if "%UNIT%%SMOKE%"=="00" (echo All checks passed.) else (echo Some checks FAILED - see above.)
pause
exit /b 0

rem ---- portable build ----------------------------------------------------------
:build
echo Making a portable copy in dist\TeleScore ...
if exist "dist\TeleScore" rmdir /s /q "dist\TeleScore"
robocopy "%RT%" "dist\TeleScore" /E /NFL /NDL /NJH /NJS /NP >nul
ren "dist\TeleScore\electron.exe" TeleScore.exe
if exist "dist\TeleScore\resources\default_app.asar" del "dist\TeleScore\resources\default_app.asar"
robocopy "app" "dist\TeleScore\resources\app\app" /E /NFL /NDL /NJH /NJS /NP >nul
copy /y package.json "dist\TeleScore\resources\app\" >nul
copy /y LICENSE "dist\TeleScore\resources\app\" >nul 2>&1
echo Done: dist\TeleScore\TeleScore.exe  (copy the whole TeleScore folder to move it)
pause
exit /b 0

:fail
echo.
echo TeleScore could not start. See the message above.
pause
exit /b 1
