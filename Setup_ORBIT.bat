@echo off
setlocal
cd /d "%~dp0" || exit /b 1
title ORBIT - Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %*
set "orbit_status=%errorlevel%"
if not "%orbit_status%"=="0" echo Setup failed. Review the error above.
if "%orbit_status%"=="0" echo Setup finished. Open Run_ORBIT.bat to launch ORBIT.
if /i not "%~1"=="-NonInteractive" pause
exit /b %orbit_status%
