@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Flask не установился. Проверь Python и интернет.
  pause
  exit /b 1
)
start "Moon Cinema" http://127.0.0.1:5000
python app.py
pause
