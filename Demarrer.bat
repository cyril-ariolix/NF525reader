@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo NF525 - Factures presentes dans les archives
echo.

set "PY="
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY=py -3"
) else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY=python"
    ) else (
        echo Python 3 est requis. Installez-le depuis https://www.python.org/downloads/
        echo Cochez "Add python.exe to PATH" pendant l'installation.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement Python (premiere utilisation)...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Impossible de creer .venv
        pause
        exit /b 1
    )
)

echo Installation des dependances...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo Echec de l'installation des dependances.
    pause
    exit /b 1
)

set "PYTHONPATH=."

echo.
echo Demarrage de l'application...
echo Laissez cette fenetre ouverte. Fermez-la pour arreter l'application.
echo.

start "" cmd /c "ping -n 4 127.0.0.1 >nul && start http://localhost:8501"

".venv\Scripts\python.exe" -m streamlit run app.py

if errorlevel 1 (
    echo.
    echo L'application s'est arretee avec une erreur.
    pause
)
