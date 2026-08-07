@echo off
title Crowdfunding Enterprise CRM - Live Dev Mode
color 0B

echo ========================================================
echo   Launching Full-Stack Dev Mode (Vite + FastAPI Uvicorn)
echo ========================================================
echo.

echo [1/2] Launching React Vite Dev Server (http://localhost:5173)...
start "React Vite Frontend (Dev)" cmd /k "cd frontend && npm run dev"

echo [2/2] Launching FastAPI Backend Engine (http://127.0.0.1:8000)...
start "" http://localhost:5173

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause
