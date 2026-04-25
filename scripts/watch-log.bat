@echo off
cd /d %~dp0..
if exist ".venv\Scripts\python.exe" (
  set "PTBR_PY=.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set "PTBR_PY=py -3"
  ) else (
    set "PTBR_PY=python"
  )
)
%PTBR_PY% -m src.tools.tail_log --follow --lines 80 %*
exit /b %errorlevel%
