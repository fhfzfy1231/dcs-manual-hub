@echo off
cd /d "%~dp0"
title DCS Manual Hub AI v2.3

echo ========================================================
echo        DCS Manual Hub AI - Quick Launcher
echo ========================================================
echo.
echo [1/3] Python environment:
python --version
echo.
echo [2/3] Checking requirements...
python -m pip install -r requirements.txt
echo.
echo [3/3] Starting server at http://localhost:8000 ...
start http://localhost:8000
python -m uvicorn app:app --host 0.0.0.0 --port 8000
echo.
echo ========================================================
echo Process exited. Press any key to close...
echo ========================================================
pause
