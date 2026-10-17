@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - multi intersection launcher (2x2 view)
REM
REM  Analyses every intersection listed under multi_view.cameras
REM  in configs\app_config.yaml at the same time and shows them
REM  in one tiled window. Press Q on the window to stop; each
REM  intersection then writes its own reports.
REM
REM  Extra arguments are passed through, for example:
REM    run_multi.bat cctv.max_duration_secs=3600
REM
REM  IMPORTANT: ASCII-only, same reason as run.bat.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHONDONTWRITEBYTECODE=1"

call "%~dp0_find_python.bat"
if errorlevel 1 exit /b 1

echo [INFO] Python folder : !PYEXE!
echo [INFO] Starting multi intersection analysis. Press Q on the window to stop.
echo.

"!PYEXE!" multi_view.py %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo [ERROR] Program exited with code %EXITCODE%.
    echo         Read the messages above to see what went wrong.
) else (
    echo [INFO] Finished. Reports were written to the "outputs" folder.
)
echo.
pause
endlocal
