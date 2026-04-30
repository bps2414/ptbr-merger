@echo off
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start-ptbrmerger-hidden.ps1"
exit /b %errorlevel%
