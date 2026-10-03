@echo off
REM ============================================================
REM  Shared helper: locate the python executable of the conda
REM  environment and expose it as PYEXE.
REM
REM  Called by run.bat / edit_zones.bat / check_accuracy.bat /
REM  run_tests.bat so the lookup logic lives in one place only.
REM  Sets errorlevel 1 when the environment cannot be found.
REM
REM  IMPORTANT: ASCII-only, same reason as the other batch files.
REM ============================================================

set "ENV_NAME=traffic"
set "PYEXE="

if exist "%USERPROFILE%\anaconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=%USERPROFILE%\anaconda3\envs\%ENV_NAME%\python.exe"
)
if not defined PYEXE if exist "%USERPROFILE%\miniconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=%USERPROFILE%\miniconda3\envs\%ENV_NAME%\python.exe"
)
if not defined PYEXE if exist "C:\ProgramData\anaconda3\envs\%ENV_NAME%\python.exe" (
    set "PYEXE=C:\ProgramData\anaconda3\envs\%ENV_NAME%\python.exe"
)

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

exit /b 0
