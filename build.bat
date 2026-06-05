@echo off
title Fleet Monitor Pro — Compilando...
cd /d "%~dp0"

echo.
echo  Fleet Monitor Pro — Generador de ejecutable portable
echo  ======================================================
echo.

:: Comprobar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python no encontrado.
    echo  Descargalo de https://www.python.org/downloads/
    pause & exit /b 1
)

:: Crear/activar entorno virtual
if not exist "venv\" (
    echo  Creando entorno virtual...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Instalar dependencias de la app + PyInstaller
echo  Instalando dependencias...
pip install -q -r requirements.txt
pip install -q pyinstaller

:: Limpiar builds anteriores
if exist "dist\FleetMonitorPro" rmdir /s /q "dist\FleetMonitorPro"
if exist "build\FleetMonitorPro"  rmdir /s /q "build\FleetMonitorPro"

:: Compilar
echo.
echo  Compilando (puede tardar 1-3 minutos)...
echo.
pyinstaller fleet_monitor.spec --noconfirm

if errorlevel 1 (
    echo.
    echo  ERROR durante la compilacion. Revisa los mensajes anteriores.
    pause & exit /b 1
)

echo.
echo  =====================================================
echo   Listo! Ejecutable en: dist\FleetMonitorPro\
echo   Copia toda esa carpeta al PC de destino.
echo   Ejecuta: FleetMonitorPro.exe
echo  =====================================================
echo.
pause
