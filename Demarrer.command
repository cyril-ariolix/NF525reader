#!/bin/bash
cd "$(dirname "$0")"
chmod +x "$0" 2>/dev/null || true

echo "NF525 - Factures présentes dans les archives"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 est requis."
    echo "Installez-le depuis https://www.python.org/downloads/ ou via Homebrew : brew install python3"
    read -r -p "Appuyez sur Entrée pour fermer…"
    exit 1
fi

VENV_PY=".venv/bin/python3"
if [ ! -x "$VENV_PY" ] || ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    echo "Création de l'environnement Python…"
    rm -rf .venv
    python3 -m venv .venv || exit 1
fi

echo "Installation des dépendances…"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r requirements.txt || exit 1

export PYTHONPATH=.

echo
echo "Démarrage de l'application…"
echo "Laissez cette fenêtre ouverte. Fermez-la pour arrêter l'application."
echo

(sleep 3 && open "http://localhost:8501") &

"$VENV_PY" -m streamlit run app.py

if [ $? -ne 0 ]; then
    echo
    echo "L'application s'est arrêtée avec une erreur."
    read -r -p "Appuyez sur Entrée pour fermer…"
fi
