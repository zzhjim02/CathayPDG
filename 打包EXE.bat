@echo off
rem Build single-file EXE for CathayPDG
setlocal
cd /d "%~dp0"
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name CathayPDG ^
  --icon app.ico --add-data "config;config" --add-data "app.ico;." ^
  --collect-all tkinterdnd2 --collect-all pyzipper --hidden-import Crypto gui.py
if errorlevel 1 (
  echo [ERROR] build failed
  pause
  exit /b 1
)
if not exist dist\Release mkdir dist\Release
move /y dist\CathayPDG.exe dist\Release\CathayPDG.exe >nul
echo Done: dist\Release\CathayPDG.exe
pause
