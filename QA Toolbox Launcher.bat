@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Text-menu stand-in for QA Toolbox Launcher.exe, for when the packaged
REM exe is unavailable (e.g. quarantined by endpoint security software like
REM SentinelOne, which commonly flags unsigned PyInstaller --onefile builds).
REM Backup/reset/restore delegate to scripts\toolbox_cli.py so the logic
REM stays identical to the GUI launcher (see app\toolbox_ops.py).

set VENV_PY=.venv\Scripts\python.exe
set HOST=127.0.0.1
set PORT=8000

:menu
cls
echo ================================
echo   QA Toolbox Launcher (batch)
echo ================================
echo.
echo  1. Setup / Install Dependencies
echo  2. Start server
echo  3. Stop server
echo  4. Open in browser
echo  5. Backup Data (db + images)
echo  6. Import Backup...
echo  7. Reset / Clear All Data
echo  8. Exit
echo.
set /p CHOICE=Choose an option (1-8):

if "%CHOICE%"=="1" goto setup
if "%CHOICE%"=="2" goto start
if "%CHOICE%"=="3" goto stop
if "%CHOICE%"=="4" goto openbrowser
if "%CHOICE%"=="5" goto backup
if "%CHOICE%"=="6" goto import
if "%CHOICE%"=="7" goto reset
if "%CHOICE%"=="8" goto end
goto menu

:setup
echo.
if exist "%VENV_PY%" (
    echo Virtual environment already exists.
) else (
    where py >nul 2>nul
    if !errorlevel! == 0 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if !errorlevel! == 0 (
            python -m venv .venv
        ) else (
            echo No Python interpreter found on PATH. Install Python 3 first.
            pause
            goto menu
        )
    )
)
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
echo.
echo Setup complete.
pause
goto menu

:start
if not exist "%VENV_PY%" (
    echo No environment found yet. Run "Setup / Install Dependencies" first.
    pause
    goto menu
)
start "QA Toolbox Server" "%VENV_PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%
echo.
echo Server starting in a new window. Give it a few seconds, then use
echo "Open in browser" (option 4) or go to http://%HOST%:%PORT%
pause
goto menu

:stop
echo.
echo Stopping any running QA Toolbox server...
"%VENV_PY%" scripts\toolbox_cli.py stop-server
pause
goto menu

:openbrowser
start http://%HOST%:%PORT%
goto menu

:backup
if not exist "%VENV_PY%" (
    echo No environment found yet. Run "Setup / Install Dependencies" first.
    pause
    goto menu
)
"%VENV_PY%" scripts\toolbox_cli.py backup
pause
goto menu

:import
if not exist "%VENV_PY%" (
    echo No environment found yet. Run "Setup / Install Dependencies" first.
    pause
    goto menu
)
echo.
echo This replaces the current database and all screenshots/exports.
echo Back up first if you haven't already (option 5).
echo.
set /p BACKUPZIP=Full path to the backup .zip file:
if not exist "!BACKUPZIP!" (
    echo File not found: !BACKUPZIP!
    pause
    goto menu
)
set /p CONFIRM=Type YES to overwrite current data with this backup:
if /i not "!CONFIRM!"=="YES" (
    echo Cancelled.
    pause
    goto menu
)
"%VENV_PY%" scripts\toolbox_cli.py restore "!BACKUPZIP!"
pause
goto menu

:reset
echo.
echo This PERMANENTLY DELETES the database and all screenshots/exports.
echo This cannot be undone.
echo.
set /p CONFIRM=Type DELETE ALL to confirm:
if not "!CONFIRM!"=="DELETE ALL" (
    echo Cancelled.
    pause
    goto menu
)
"%VENV_PY%" scripts\toolbox_cli.py reset --yes
pause
goto menu

:end
endlocal
exit /b
