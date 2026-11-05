@echo off
REM Builds dist\Groundwork Save Editor.exe (one file, no console).
REM Note: PyInstaller fails if this folder and its temp/spec dirs are on different drives; build from a local drive.
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller || goto :fail
python -m PyInstaller --noconfirm --onefile --windowed --name "Groundwork Save Editor" ^
  --icon media\icon.ico --add-data "media\icon.ico;." --collect-all customtkinter --exclude-module pkg_resources app.py || goto :fail
echo.
echo Built: dist\Groundwork Save Editor.exe
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
