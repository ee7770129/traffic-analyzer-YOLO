@echo off
REM ============================================================
REM  TrafficAnalyzer_TW - zone polygon editor
REM
REM  Draw the detection area of each approach road directly on a
REM  frame of the video, and save it to configs/roads_polygons.json
REM
REM  You MUST redraw the zones whenever you switch to a different
REM  video, otherwise every count will be meaningless.
REM
REM  Pass-through arguments, for example:
REM      edit_zones.bat --video test_videos/my.mp4 --frame 300
REM
REM  IMPORTANT: ASCII-only. cmd.exe reads .bat files with the OEM
REM  codepage before chcp can take effect, so non-ASCII characters
REM  here would be mis-parsed and the window would close instantly.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"

call "%~dp0_find_python.bat"
if errorlevel 1 exit /b 1

echo.
echo  Zone editor controls:
echo    Left click   add a vertex
echo    Right click  finish the current zone (3 vertices minimum)
echo    N / U / D    finish zone / undo vertex / delete last zone
echo    C / S / Q    clear all / save / quit
echo    + / -        zoom the view (does not affect saved coordinates)
echo.

"!PYEXE!" tools\zone_editor.py %*

echo.
pause
endlocal
