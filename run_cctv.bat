@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - live intersection CCTV launcher
REM
REM  Usage:
REM    run_cctv.bat                      default intersection
REM    run_cctv.bat wuquannan_gaogong    pick another preset
REM    run_cctv.bat wuquan_fuxing cctv.max_duration_secs=3600
REM
REM  Preset names are listed in configs\cctv_cameras.yaml.
REM  Press Q on the video window to stop and write the reports.
REM
REM  IMPORTANT: ASCII-only, same reason as run.bat.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CAMERA=%~1"
if "%CAMERA%"=="" set "CAMERA=wuquan_fuxing"

echo [INFO] Intersection preset: %CAMERA%
echo.

call "%~dp0run.bat" cctv.camera=%CAMERA% video_writer_node.fps=10 %2 %3 %4 %5 %6 %7 %8 %9

endlocal
