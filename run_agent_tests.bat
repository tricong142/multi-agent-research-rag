@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv\Scripts\python.exe. Use the project Python environment.
    pause
    exit /b 1
)
if "%~1"=="" (
    ".venv\Scripts\python.exe" -m research_rag.evaluation.local_demo --agent all
) else (
    ".venv\Scripts\python.exe" -m research_rag.evaluation.local_demo --agent "%~1"
)
set "demo_exit=%errorlevel%"
echo.
echo Open the report.html path printed above. Exit %demo_exit% is diagnostic status, not model accuracy.
pause
exit /b %demo_exit%
