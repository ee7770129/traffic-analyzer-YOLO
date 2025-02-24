@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - one click launcher (live preview)
REM
REM  IMPORTANT: this file is intentionally ASCII-only.
REM  cmd.exe reads .bat files using the OEM codepage before any
REM  chcp can take effect, so non-ASCII characters here would be
REM  mis-parsed as commands and the window would close instantly.
REM  All Chinese documentation lives in CLAUDE.md instead.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Keep the project tree clean: do not scatter __pycache__ folders around.
REM The startup cost of skipping the bytecode cache is negligible here,
REM since the run is dominated by model inference.
set "PYTHONDONTWRITEBYTECODE=1"

set "ENV_NAME=traffic"
set "PYEXE="

REM --- 1) look for the conda environment in the usual places ---
if exist "%USERPROFILE%\anaconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=%USERPROFILE%\anaconda3\envs\%ENV_NAME%\python.exe"
)
if not defined PYEXE if exist "%USERPROFILE%\miniconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=%USERPROFILE%\miniconda3\envs\%ENV_NAME%\python.exe"
)
if not defined PYEXE if exist "C:\ProgramData\anaconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=C:\ProgramData\anaconda3\envs\%ENV_NAME%\python.exe"
)

REM --- 2) otherwise ask conda where the environment lives ---
if not defined PYEXE (
    echo [INFO] Locating conda environment "%ENV_NAME%" ...
    for /f "usebackq delims=" %%i in (`conda run -n %ENV_NAME% python -c "import sys;print(sys.executable)" 2^>nul`) do (
        set "PYEXE=%%i"
    )
)

if not defined PYEXE (
    echo.
    echo [ERROR] Could not find python for conda environment "%ENV_NAME%".
    echo         Please create the environment first:
    echo.
    echo           conda create --name %ENV_NAME% python=3.10 -y
    echo           conda activate %ENV_NAME%
    echo           pip install torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cu121
    echo           pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [INFO] Python folder : !PYEXE!
echo [INFO] Working folder: %CD%
echo [INFO] Starting analysis. Press Q on the video window to stop early.
echo.

"!PYEXE!" main.py %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo [ERROR] Program exited with code %EXITCODE%.
    echo         Read the messages above to see what went wrong.
) else (
    echo [INFO] Finished. CSV reports were written to the "outputs" folder.
)
echo.
pause
endlocal
