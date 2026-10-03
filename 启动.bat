@echo off
rem CathayPDG launcher (pure ASCII on purpose)
setlocal
set HERE=%~dp0
set PYEXE=

rem 1) Portable runtime that ships with the package.
rem    It lives in 程序组件\runtime (one level up from this 开发 folder),
rem    so look there first -- that way the user needs nothing installed.
if exist "%HERE%..\runtime\pythonw.exe" set PYEXE=%HERE%..\runtime\pythonw.exe
if not defined PYEXE (
  if exist "%HERE%runtime\pythonw.exe" set PYEXE=%HERE%runtime\pythonw.exe
)
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
  echo [ERROR] No usable Python found.
  echo.
  echo   Easy fix: the portable runtime (a full Python with all packages already
  echo   installed) should sit in "程序组件\runtime". Copy this whole folder with it,
  echo   don't move 启动.bat out on its own.
  echo.
  echo   Or install Python 3.10+ yourself and run: 安装依赖.bat
  pause
  exit /b 1
)

rem Commands that print to the console need python.exe, not pythonw.exe
if /i "%~1"=="--selftest" goto :console
if /i "%~1"=="--check-deps" goto :console
goto :gui

:console
set CONEXE=%PYEXE:pythonw.exe=python.exe%
"%CONEXE%" "%HERE%gui.py" %1
echo.
pause
exit /b %errorlevel%

:gui
start "" "%PYEXE%" "%HERE%gui.py"
