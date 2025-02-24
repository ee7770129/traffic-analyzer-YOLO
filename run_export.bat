@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - batch export launcher
REM
REM  Runs the analysis WITHOUT a preview window and writes both
REM  the annotated result video and the CSV reports.
REM  Use this one when you want the deliverables, not a live view.
REM
REM  IMPORTANT: ASCII-only, same reason as run.bat.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [INFO] Batch export mode: no preview window, video + reports will be saved.
echo.

call "%~dp0run.bat" pipeline.show_window=false pipeline.save_video=true %*

endlocal
