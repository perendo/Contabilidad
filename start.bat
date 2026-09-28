@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV=%PROJECT_ROOT%.venv\Scripts\activate.bat"

if not exist "%VENV%" (
    echo No se encontro el entorno virtual en:
    echo %PROJECT_ROOT%.venv
    pause
    exit /b 1
)

call "%VENV%"
set "PYTHONPATH=%PROJECT_ROOT%backend\src"
cd /d "%PROJECT_ROOT%backend"

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

pause