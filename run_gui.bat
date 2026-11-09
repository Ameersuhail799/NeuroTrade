@echo off
cd /d "%~dp0"
echo Starting NeuroTrade AI...
call .\.venv\Scripts\python.exe neurotrade.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo NeuroTrade AI exited with error code %ERRORLEVEL%.
    pause
)
