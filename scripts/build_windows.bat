@echo off
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required on this Windows computer.
  pause
  exit /b 1
)

if not exist .venv-windows\Scripts\python.exe (
  python -m venv .venv-windows
)
call .venv-windows\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
pyinstaller --noconfirm --clean --windowed --onefile --icon assets\dake-desk-icon.ico --add-data "assets;assets" --paths src --collect-all windows_toasts --collect-all winrt ^
  --hidden-import app_paths ^
  --hidden-import services.hotkey ^
  --hidden-import services.windows_notifications ^
  --hidden-import storage.database ^
  --hidden-import ui.main_window ^
  --hidden-import ui.task_dialog ^
  --hidden-import ui.float_window ^
  --hidden-import ui.settings_dialog ^
  --hidden-import ui.theme ^
  --hidden-import ui.controls --hidden-import ui.workspace_editor --hidden-import ui.important_reminder --hidden-import ui.task_steps --hidden-import ui.desktop_note ^
  --name DaKeDesk src\main.py
if errorlevel 1 (
  echo Program build failed. Please keep this window open and send the error text or screenshot.
  pause
  exit /b 1
)

set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" (
  echo.
  echo Program build complete: dist\DaKeDesk.exe
  echo To create Setup.exe, install Inno Setup once and run this script again.
  pause
  exit /b 0
)

"%ISCC_PATH%" scripts\installer.iss
echo.
echo Installer complete: release\DaKeDesk-Setup.exe
pause
