@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Missing virtual environment Python:
  echo   %PYTHON_EXE%
  echo.
  echo Create or repair the venv, then install requirements.
  exit /b 1
)

cd /d "%ROOT_DIR%"
"%PYTHON_EXE%" -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
