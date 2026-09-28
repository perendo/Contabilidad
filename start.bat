@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "VENV_ACTIVATE=%PROJECT_ROOT%.venv\Scripts\activate.bat"
set "VENV_PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "LAUNCHER=%PROJECT_ROOT%scripts\dev_start.py"

if not exist "%VENV_PYTHON%" (
    echo No se encontro el entorno virtual en:
    echo %PROJECT_ROOT%.venv
    echo Crealo con:  python -m venv .venv
    echo Y luego instala las dependencias:  .venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

call "%VENV_ACTIVATE%"
"%VENV_PYTHON%" "%LAUNCHER%"
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo El arranque fallo o se cancelo. Revisa el mensaje de arriba.
    pause
)

exit /b %EXITCODE%
