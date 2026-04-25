@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_CMD=.venv\Scripts\python.exe"
)

if not defined PYTHON_CMD (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  python --version >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python nao encontrado.
  echo Instale Python 3.11+ ou desative o alias da Microsoft Store para python.exe.
  pause
  exit /b 1
)

call %PYTHON_CMD% -m src.web.server
pause
