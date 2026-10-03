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

REM Locating the conda environment is shared with the other launchers.
call "%~dp0_find_python.bat"
if errorlevel 1 exit /b 1

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
