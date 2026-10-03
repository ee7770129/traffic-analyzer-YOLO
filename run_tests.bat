@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - run the unit test suite
REM
REM  Runs pytest with coverage. The suite fails if total coverage
REM  drops below 70 percent (configured in pytest.ini).
REM
REM  Pass-through arguments, for example:
REM      run_tests.bat tests/test_counting_node.py
REM      run_tests.bat -k counting
REM
REM  IMPORTANT: ASCII-only, same reason as the other batch files.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call "%~dp0_find_python.bat"
if errorlevel 1 exit /b 1

echo [INFO] Running the test suite...
echo.

"!PYEXE!" -m pytest %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo [FAIL] Tests failed, or coverage is below the required threshold.
) else (
    echo [PASS] All tests passed and coverage meets the threshold.
)
echo.
pause
endlocal
