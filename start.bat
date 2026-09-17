@echo off
cd /d "%~dp0"
if not exist backend\.venv (
  echo Creating virtual environment...
  py -m venv backend\.venv
)
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
python backend\app.py
pause
