@echo off
setlocal
cd /d "%~dp0" || exit /b 1
title ORBIT
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Run Setup_ORBIT.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "main.py"
set "orbit_status=%errorlevel%"
if not "%orbit_status%"=="0" (
    echo ORBIT stopped with an error. Review the message above.
    pause
)
exit /b %orbit_status%
