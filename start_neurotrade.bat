@echo off
cd /d "%~dp0"
echo Starting NeuroTrade AI Integrated Terminal...
".\.venv\Scripts\python.exe" neurotrade.py
if errorlevel 1 (
    echo.
    echo NeuroTrade AI closed with error code %errorlevel%
    pause
)
