@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - START HERE
REM
REM  Friendly entry point: checks that the required assets are in
REM  place, explains what is missing, then hands over to run.bat.
REM  Just double-click this file.
REM
REM  IMPORTANT: ASCII-only on purpose. cmd.exe reads .bat files
REM  with the OEM codepage before chcp can take effect, so any
REM  non-ASCII character here would be mis-parsed and the window
REM  would close instantly. Chinese docs live in README.md.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ============================================================
echo    TrafficAnalyzer_TW   Intersection Traffic Flow Analyzer
echo  ============================================================
echo.

set "MISSING=0"

REM --- Asset 1: the input video -------------------------------
if exist "test_videos\test_video.mp4" goto :video_ok
set "MISSING=1"
echo  [MISSING]  test_videos\test_video.mp4
echo.
echo     The sample video is NOT included in this repository,
echo     because it belongs to the upstream project.
echo.
echo     Option A - use the upstream sample video:
echo         https://github.com/Koldim2001/TrafficAnalyzer
echo         copy test_videos\test_video.mp4 into test_videos\
echo.
echo     Option B - use your own footage:
echo         put your .mp4 in test_videos\ and run
echo             run.bat video_reader.src=test_videos/YOUR_FILE.mp4
echo         NOTE: you must also redraw configs\roads_polygons.json
echo               for your own camera view. See README.md.
echo.
:video_ok

REM --- Asset 2: the YOLO weights ------------------------------
if exist "weights\yolov8m.pt" goto :weights_ok
echo  [INFO]     weights\yolov8m.pt not found.
echo             Ultralytics will try to download it on first run
echo             ^(about 52 MB^). If the download fails, get it from
echo             https://github.com/ultralytics/assets/releases
echo             and place it in the weights\ folder.
echo.
:weights_ok

if "%MISSING%"=="1" (
    echo  ------------------------------------------------------------
    echo   Cannot start yet: please provide the file listed above.
    echo   Full instructions are in README.md
    echo  ------------------------------------------------------------
    echo.
    pause
    exit /b 1
)

echo  All required assets found. Starting...
echo.
call "%~dp0run.bat" %*

endlocal
