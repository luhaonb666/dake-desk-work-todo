@echo off
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 is required on this Windows computer.
  pause
  exit /b 1
)

if not exist .venv-windows\Scripts\python.exe python -m venv .venv-windows
call .venv-windows\Scripts\activate.bat
pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo Starting the source version. Close the app normally after testing.
python src\main.py
pause
