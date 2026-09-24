#!/bin/bash
cd "$(dirname "$0")"
chmod +x "$0" 2>/dev/null || true

echo "NF525 - Factures présentes dans les archives"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 est requis."
    echo "Sur Debian/Ubuntu : sudo apt install python3 python3-venv python3-pip"
    read -r -p "Appuyez sur Entrée pour fermer…"
    exit 1
fi

VENV_PY=".venv/bin/python3"
if [ ! -x "$VENV_PY" ] || ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "Création de l'environnement Python…"
    rm -rf .venv
    if ! python3 -m venv .venv; then
        echo
        echo "Impossible de créer l'environnement virtuel (.venv)."
        echo "Sur Debian/Ubuntu, installez le module venv, puis relancez ce script :"
        echo "  sudo apt install python3-venv"
        read -r -p "Appuyez sur Entrée pour fermer…"
        exit 1
    fi
fi

echo "Installation des dépendances…"
if ! "$VENV_PY" -m pip install -q --upgrade pip \
    || ! "$VENV_PY" -m pip install -q -r requirements.txt; then
    echo "Échec de l'installation des dépendances."
    read -r -p "Appuyez sur Entrée pour fermer…"
    exit 1
fi

export PYTHONPATH=.

echo
echo "Démarrage de l'application…"
echo "Laissez cette fenêtre ouverte. Fermez-la pour arrêter l'application."
echo

if command -v xdg-open >/dev/null 2>&1; then
    (sleep 3 && xdg-open "http://localhost:8501") &
fi

"$VENV_PY" -m streamlit run app.py

if [ $? -ne 0 ]; then
    echo
    echo "L'application s'est arrêtée avec une erreur."
    read -r -p "Appuyez sur Entrée pour fermer…"
fi
