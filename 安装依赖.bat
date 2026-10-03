@echo off
rem CathayPDG dependency installer (pure ASCII on purpose)
rem
rem NOTE: you do NOT need this if you use the packaged exe -- everything is
rem bundled inside it. This is only for people running the .py sources with
rem their own Python. See README section "依赖".
setlocal
set HERE=%~dp0
cd /d "%HERE%"

echo ============================================================
echo   CathayPDG - install dependencies
echo ============================================================
echo.
echo Using the packaged exe? Then everything is already bundled.
echo This script is for running the source (.py) with your own Python.
echo.

rem --- 1. find a Python to install into ---
set PYEXE=
py -3 -c "import sys" >nul 2>nul && set PYEXE=py -3
if not defined PYEXE (
  python -c "import sys" >nul 2>nul && set PYEXE=python
)
if not defined PYEXE (
  echo [ERROR] No Python found.
  echo.
  echo   Option A (recommended): just use the packaged exe.
  echo   Option B: install Python 3.10+ from https://www.python.org/
  echo             tick "Add Python to PATH" during setup, then rerun this.
  echo   Option C: use the portable runtime shipped in 程序组件\runtime
  echo             via 启动.bat -- its packages are already installed.
  echo.
  pause
  exit /b 1
)

echo Using: %PYEXE%
%PYEXE% -c "import sys;print('  version:', sys.version.split()[0])"
echo.

rem --- 2. make sure pip exists ---
%PYEXE% -m pip --version >nul 2>nul
if errorlevel 1 (
  echo pip is missing, bootstrapping it...
  %PYEXE% -m ensurepip --upgrade
  if errorlevel 1 (
    echo [ERROR] Could not bootstrap pip. See https://pip.pypa.io/ to install it.
    pause
    exit /b 1
  )
)

rem --- 3. install ---
echo Installing from requirements.txt ...
echo.
%PYEXE% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERROR] pip install failed.
  echo   - No internet? Download the wheels on another machine and install offline.
  echo   - Behind a proxy? Try: -m pip install -r requirements.txt --proxy http://user:pass@host:port
  echo   - pymupdf has wheels for win/amd64; a source build means your Python is
  echo     too new or too old -- Python 3.10~3.12 is the safe zone.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   Done. Running the health check:
echo ============================================================
echo.
%PYEXE% pdg_deps.py
exit /b %errorlevel%
