@echo off
rem =========================================================================
rem  NHS Elective Flow Intelligence - one-click launcher (Windows)
rem =========================================================================
rem  Starts the API and the dashboard, then opens the site in your browser.
rem  Prerequisites: "make setup" (or the manual install) and "make data"
rem  (or "make demo") have been run once before.
rem =========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] Python environment not found. Run: make setup
    pause & exit /b 1
)
if not exist "data\processed\warehouse.duckdb" (
    echo [!] No data warehouse found. Run: make data   ^(or: make demo^)
    pause & exit /b 1
)

echo Starting API on http://localhost:8000 ...
start "NHS EFI - API" cmd /k "cd /d "%~dp0backend" && set PYTHONPATH=%~dp0backend&& "%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting dashboard on http://localhost:3000 ...
if exist "frontend\.next" (
    start "NHS EFI - Dashboard" cmd /k "cd /d "%~dp0frontend" && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000&& npx next start -p 3000"
) else (
    start "NHS EFI - Dashboard" cmd /k "cd /d "%~dp0frontend" && set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000&& npx next dev -p 3000"
)

echo Waiting for the site to come up ...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000

echo.
echo   Dashboard : http://localhost:3000
echo   API docs  : http://localhost:8000/docs
echo.
echo   Close the two server windows to stop.
endlocal
