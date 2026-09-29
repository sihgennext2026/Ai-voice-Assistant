@echo off
title RoziRaah Livelihood Guidance Launcher
echo.
echo  ================================================
echo    RoziRaah - Voice-first livelihood guidance
echo  ================================================
echo.

set BACKEND_DIR=%~dp0
set FRONTEND_DIR=%~dp0VoiceAssistant

echo  [1/2] Starting backend (http://localhost:8000)...
start "RoziRaah Backend" cmd /k "cd /d "%BACKEND_DIR%" && call .venv\Scripts\activate.bat && uvicorn api:app --port 8000"

timeout /t 3 /nobreak >nul

echo  [2/2] Starting frontend (http://localhost:3000)...
start "RoziRaah Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo.
echo  ================================================
echo    Open: http://localhost:3000
echo    Backend health: http://localhost:8000/health
echo  ================================================
echo.
pause
