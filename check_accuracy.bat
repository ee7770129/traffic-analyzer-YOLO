@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - accuracy validation
REM
REM  Compares a manual vehicle count against the system count and
REM  writes an error-rate report.
REM
REM  Usage:
REM    check_accuracy.bat            compare using the newest result
REM    check_accuracy.bat template   create the blank manual-count sheet
REM    check_accuracy.bat --result outputs\20250224_143052   explicit
REM
REM  Workflow:
REM    1. check_accuracy.bat template
REM    2. fill in the counts by watching the video
REM    3. check_accuracy.bat
REM
REM  IMPORTANT: ASCII-only, same reason as the other batch files.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call "%~dp0_find_python.bat"
if errorlevel 1 exit /b 1

REM --- explicit arguments win; otherwise auto-detect the newest run ---
set "FIRST=%~1"
if "%FIRST:~0,2%"=="--" (
    "!PYEXE!" tools\accuracy_check.py %*
    goto :done
)

if not exist "outputs" (
    echo [ERROR] No "outputs" folder yet. Run the analysis first ^(START.bat^).
    echo.
    pause
    exit /b 1
)

set "LATEST="
for /f "delims=" %%i in ('dir /b /ad /o-d outputs 2^>nul') do (
    set "LATEST=%%i"
    goto :found
)
:found

if not defined LATEST (
    echo [ERROR] No analysis results found under "outputs".
    echo         Run the analysis first ^(START.bat^).
    echo.
    pause
    exit /b 1
)

echo [INFO] Using the newest result folder: outputs\!LATEST!
echo.

if /i "%~1"=="template" (
    "!PYEXE!" tools\accuracy_check.py --result "outputs\!LATEST!" --template
    echo.
    echo  Next: open the manual-count CSV created in outputs\!LATEST!,
    echo        fill in the numbers while watching the video, then run
    echo        check_accuracy.bat again with no arguments.
) else (
    "!PYEXE!" tools\accuracy_check.py --result "outputs\!LATEST!" %*
)

:done
echo.
pause
endlocal
