@echo off
echo ========================================
echo   ToonTalk Backend - FastAPI Server
echo ========================================
cd /d "D:\Downloads\video db Hackathon\toontalk\backend"
call venv\Scripts\activate.bat
echo Starting backend on http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo Press CTRL+C to stop
echo.
python main.py
pause
