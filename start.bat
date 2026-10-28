@echo off
REM Quote-to-Delivery: double-click to start on Windows.
REM Installs what it needs the first time, builds the web app, and opens http://localhost:8000
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11 or newer is needed: https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^) & pause & exit /b 1)
where npm >nul 2>nul || (echo Node.js 20 or newer is needed: https://nodejs.org/ & pause & exit /b 1)
if not exist .env copy .env.example .env >nul

echo 1/3 Setting up the backend...
cd backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip >nul
pip install -q -r requirements.txt || (echo Backend install failed. & pause & exit /b 1)

echo 2/3 Building the web app...
cd ..\frontend
if not exist node_modules call npm install --silent
call npm run build --silent >nul || (echo Web app build failed. & pause & exit /b 1)

echo 3/3 Starting on http://localhost:8000  (close this window to stop)
cd ..\backend
start "" http://localhost:8000
python -m uvicorn app.main:app --port 8000
pause
