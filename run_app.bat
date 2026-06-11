@echo off
echo =========================================================
echo       Starting AyuReg Clinical Assistant Portal
echo =========================================================

echo Starting Python FastAPI Backend Server...
start cmd /k "call venv\Scripts\activate.bat && uvicorn backend.main:app --reload --port 8000"

echo Starting React Frontend Dev Server...
start cmd /k "cd frontend && npm run dev"

echo.
echo AyuReg is booting up:
echo - Frontend Clinical Client: http://localhost:5173
echo - Backend FastAPI Engine:    http://localhost:8000
echo.
echo Press any key to close this launcher...
pause > nul
