@echo off
title Fleet Monitor Pro
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python no encontrado. Descargalo de https://www.python.org/downloads/
    pause & exit /b 1
)

if not exist "venv\" (
    echo Creando entorno virtual...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Comprobando dependencias...
pip install -q -r requirements.txt

set PYTHONWARNINGS=ignore::RuntimeWarning
python xerox_monitor.py
