@echo off
title Multi-Agent Research RAG - Local Interactive Studio
echo ======================================================================
echo    STARTING MULTI-AGENT RESEARCH RAG INTERACTIVE WEB STUDIO
echo ======================================================================
echo.
echo Opening browser at http://127.0.0.1:8080 ...
start http://127.0.0.1:8080
echo.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe web_demo\server.py 8080
) else (
    python web_demo\server.py 8080
)
pause
