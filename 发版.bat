@echo off
setlocal
cd /d "%~dp0"
py -3 fab.py %*
if errorlevel 1 (
  echo [ERROR] build failed
)
pause
