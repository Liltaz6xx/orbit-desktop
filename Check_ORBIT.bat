@echo off
setlocal
cd /d "%~dp0" || exit /b 1
title ORBIT - System Check
set "orbit_status=1"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run Setup_ORBIT.bat first.
) else (
    ".venv\Scripts\python.exe" -m orbit.diagnostics
)
if exist ".venv\Scripts\python.exe" set "orbit_status=%errorlevel%"
if /i not "%~1"=="--no-pause" pause
exit /b %orbit_status%
