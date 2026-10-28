#!/usr/bin/env bash
# Quote-to-Delivery: one-command start for macOS and Linux.
# Installs what it needs the first time, builds the web app, and opens http://localhost:8000
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11 or newer is needed: https://www.python.org/downloads/"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Node.js 20 or newer is needed: https://nodejs.org/"; exit 1; }
[ -f .env ] || cp .env.example .env

echo "1/3 Setting up the backend..."
cd backend
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip >/dev/null
pip install -q -r requirements.txt

echo "2/3 Building the web app..."
cd ../frontend
[ -d node_modules ] || npm install --silent
npm run build --silent >/dev/null

echo "3/3 Starting on http://localhost:$PORT  (press Ctrl+C to stop)"
cd ../backend
( sleep 3; (open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1 ) &
exec python -m uvicorn app.main:app --port "$PORT"
