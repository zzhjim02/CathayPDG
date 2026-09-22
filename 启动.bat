@echo off
rem CathayPDG launcher (pure ASCII on purpose)
setlocal
set HERE=%~dp0
set PYEXE=
if exist "%HERE%runtime\pythonw.exe" set PYEXE=%HERE%runtime\pythonw.exe
if not defined PYEXE (
  py -3 -c "import tkinter, fitz, PIL, pyzipper" >nul 2>nul && set PYEXE=py -3
)
if not defined PYEXE (
  python -c "import tkinter, fitz, PIL, pyzipper" >nul 2>nul && set PYEXE=python
)
if not defined PYEXE (
  for %%P in ("%ProgramFiles%\Python313\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe" "%ProgramFiles%\Python310\python.exe" "%LOCALAPPDATA%\Programs\Python\Python313\python.exe") do (
    if exist %%P (
      %%~P -c "import tkinter, fitz, PIL, pyzipper" >nul 2>nul && set PYEXE=%%~P
    )
  )
)
if not defined PYEXE (
  echo [ERROR] No usable Python found. Please unzip the portable runtime next to this file,
  echo         or install Python 3.10+ with: pip install pillow pymupdf pyzipper pycryptodome
  pause
  exit /b 1
)
if /i "%~1"=="--selftest" (
  "%PYEXE%" "%HERE%gui.py" --selftest
  pause
  exit /b %errorlevel%
)
start "" "%PYEXE%" "%HERE%gui.py"
