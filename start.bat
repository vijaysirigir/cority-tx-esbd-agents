@echo off
REM ============================================================
REM  Cority ESBD Agent Suite - launcher
REM ============================================================
cd /d "%~dp0backend"
echo.
echo   Starting Cority ESBD Agent Suite...
echo   Open http://127.0.0.1:5000 in your browser.
echo   (Press Ctrl+C in this window to stop.)
echo.
python app.py
pause
