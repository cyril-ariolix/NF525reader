# NF525 — Factures présentes dans les archives

Application locale pour rechercher et imprimer les factures fiscales NF525 à partir des sauvegardes d’archives hôtelières.

L’outil fonctionne **entièrement sur l’ordinateur du client** : aucune connexion Internet n’est nécessaire après l’installation. Les données restent locales dans une base SQLite (`data/hotel_group_archive.db`).

---

## Livraison au client

### Contenu du dossier à remettre

Remettez le dossier du projet **sans** le dossier `.venv` (il sera recréé au premier lancement). Incluez :

| Élément | Obligatoire | Rôle |
|---------|-------------|------|
| `Demarrer.bat` | Oui (Windows) | Lance l’application en un double-clic |
| `Demarrer.command` | Oui (Mac) | Idem sur macOS |
| `Demarrer.sh` | Oui (Linux) | Idem sur Linux / ChromeOS |
| `app.py`, `src/`, `requirements.txt` | Oui | Application |
| `.streamlit/` | Oui | Configuration (pas de mot de passe au démarrage) |
| `README.md` | Oui | Ce guide |
| `data/hotel_group_archive.db` | Optionnel | Base déjà importée — le client peut chercher tout de suite |

**Ne pas inclure** : `.venv`, fichiers `__pycache__`, archives ZIP de test volumineuses (sauf si le client doit réimporter lui-même).

### Deux modes de livraison

| Mode | Contenu | Avantage |
|------|---------|----------|
| **A — Outil seul** | Dossier sans base | Léger ; le client importe ses propres exports NF525 |
| **B — Prêt à l’emploi** | Dossier + `data/hotel_group_archive.db` déjà remplie | Recherche immédiate, sans attendre l’import (30–60 min) |

Le mode B convient lorsque vous avez déjà importé les archives pour le client.

### Prérequis sur l’ordinateur du client

- **Python 3.11 ou plus récent** installé sur le système  
  - [python.org/downloads](https://www.python.org/downloads/) (Windows / Mac)  
  - Linux : souvent déjà présent ; sinon `sudo apt install python3 python3-venv`
- **Windows** : cocher *« Add Python to PATH »* lors de l’installation
- **Espace disque** : prévoir plusieurs Go si les archives NF525 sont volumineuses (la base SQLite grossit avec les imports)
- **Navigateur** : Chrome, Edge, Firefox ou Safari récent

Aucun serveur web, Docker ou MySQL n’est requis.

---

## Démarrer l’application

**Windows** — double-cliquez sur [`Demarrer.bat`](Demarrer.bat).

**Mac** — double-cliquez sur [`Demarrer.command`](Demarrer.command).  
Si macOS refuse d’ouvrir le fichier, faites un clic droit → **Ouvrir**, ou exécutez une fois dans le Terminal :

```bash
chmod +x Demarrer.command
```

**Linux (Debian, Ubuntu, ChromeOS…)** — dans un terminal, depuis le dossier du projet :

```bash
chmod +x Demarrer.sh
./Demarrer.sh
```

Si la création de l’environnement échoue, installez le module venv : `sudo apt install python3-venv`

Au premier lancement, le script crée un environnement Python (`.venv`), installe les dépendances, démarre l’application et ouvre votre navigateur sur **http://localhost:8501**.

Laissez la fenêtre du terminal ouverte tant que vous utilisez l’application. Fermez-la pour quitter.

### Installation détaillée par système

#### Windows

1. Installer Python 3.11+ depuis [python.org](https://www.python.org/downloads/) en cochant **Add Python to PATH**.
2. Copier le dossier du projet sur le poste (Bureau, Documents, etc.).
3. Double-cliquer sur `Demarrer.bat`.
4. Au premier lancement : patienter pendant la création de `.venv` et l’installation des paquets (quelques minutes).
5. Le navigateur s’ouvre sur `http://localhost:8501`.

#### macOS

1. Installer Python 3.11+ (python.org ou Homebrew : `brew install python@3.12`).
2. Copier le dossier du projet.
3. Double-cliquer sur `Demarrer.command`.  
   Si macOS bloque : clic droit → **Ouvrir**, ou dans le Terminal :
   ```bash
   chmod +x Demarrer.command
   ./Demarrer.command
   ```

#### Linux / ChromeOS (Debian)

1. Installer Python et venv si nécessaire :
   ```bash
   sudo apt update
   sudo apt install python3 python3-venv
   ```
2. Ouvrir un terminal dans le dossier du projet :
   ```bash
   chmod +x Demarrer.sh
   ./Demarrer.sh
   ```

---

## Utilisation

### Parcours type

1. **Démarrer** — lancer le script adapté à votre OS (`Demarrer.bat`, `.command` ou `.sh`).
2. **Importer une sauvegarde** (si la base est vide) — dans la barre latérale, section *Importer une sauvegarde*, déposer le fichier ZIP d’export NF525.  
   Le nom doit ressembler à : `ExportNF525_NomHotel_FR005082.zip`  
   L’import d’une archive complète peut prendre **30 à 60 minutes** ; le compteur *Import en cours… 12 sur 2658* confirme que tout fonctionne. **Ne pas fermer la fenêtre du terminal** pendant l’import.
3. **Rechercher** — utiliser le formulaire de recherche et les filtres de la barre latérale :
   - hôtel, plage de dates ;
   - type de document (facture, avoir, etc.) ;
   - montants, mode de paiement ;
   - texte libre (client, numéro de facture, prestation).
   La recherche porte sur **toute la base**, pas seulement la page affichée.
4. **Sélectionner une facture** — cliquer sur une ligne du tableau des résultats.
5. **Télécharger** — bouton *Télécharger la facture (PDF)* pour obtenir une facture au format A4, prête pour l’impression ou l’archivage comptable.

### Aperçu et détail

- Les métadonnées de la facture sélectionnée s’affichent sous le tableau.
- Un aperçu HTML de l’archive d’origine est disponible dans un panneau repliable.
- Le PDF généré reprend les informations structurées (en-tête, lignes, totaux) dans un format lisible pour un expert-comptable.

### Fichiers d’archive acceptés

- **Archive racine** : `ExportNF525_{nom}_{code}.zip` (ex. `ExportNF525_HotelCezanne_FR005082.zip`)
- À l’intérieur : archives journalières / mensuelles `NF525CashData_*.zip`
- Le code hôtel est lu depuis le nom du fichier (ex. `FR005082`), pas depuis le SIRET

La base de données est enregistrée dans `data/hotel_group_archive.db` (créée automatiquement au premier import).

---

## Dépannage

| Problème | Cause probable | Solution |
|----------|----------------|----------|
| `python` ou `python3` introuvable | Python non installé ou absent du PATH | Réinstaller Python en cochant *Add to PATH* (Windows) ou `sudo apt install python3` (Linux) |
| Échec création de `.venv` | Module `venv` manquant (Linux) | `sudo apt install python3-venv`, puis relancer le script |
| Le navigateur ne s’ouvre pas | Pare-feu ou port occupé | Ouvrir manuellement **http://localhost:8501** |
| Page « connexion refusée » | Application non démarrée ou terminal fermé | Relancer `Demarrer.*` et garder le terminal ouvert |
| Import bloqué ou très lent | Archive volumineuse (normal) | Attendre ; suivre le compteur dans l’interface |
| Erreur « nom de fichier non reconnu » | ZIP renommé ou mauvais format | Utiliser un fichier `ExportNF525_….zip` au format attendu, sans le renommer |
| Caractères `?` dans un ancien PDF | Version antérieure de l’outil | Mettre à jour le projet ; les PDF récents utilisent l’encodage Windows (€, tirets) |
| Demande d’e-mail / mot de passe Streamlit | Config manquante | Vérifier que le dossier `.streamlit/` est présent dans le livrable |

### Réimporter ou mettre à jour les données

- Déposer un nouvel export dans *Importer une sauvegarde* : les doublons sont gérés (priorité année > mensuel > plage > journalier).
- Pour repartir de zéro : supprimer `data/hotel_group_archive.db` puis relancer un import complet.

---

## Message type pour le client

Vous pouvez adapter ce texte dans votre e-mail de livraison :

> Bonjour,
>
> Vous trouverez ci-joint l’outil **NF525 — Factures présentes dans les archives**, qui permet de rechercher et d’exporter en PDF les factures issues de vos sauvegardes NF525.
>
> **Pour démarrer**
> - **Windows** : double-cliquez sur `Demarrer.bat`
> - **Mac** : double-cliquez sur `Demarrer.command`
> - **Linux** : exécutez `./Demarrer.sh` dans un terminal
>
> Au premier lancement, l’installation des composants peut prendre quelques minutes. Le navigateur s’ouvrira sur une adresse locale (http://localhost:8501). **Laissez la fenêtre noire (terminal) ouverte** pendant toute l’utilisation.
>
> **Premier usage** : si la base n’a pas été fournie pré-importée, importez votre fichier `ExportNF525_….zip` via le panneau latéral. Comptez 30 à 60 minutes pour une archive complète.
>
> **Ensuite** : recherchez par date, client ou numéro, sélectionnez une ligne, puis téléchargez le PDF.
>
> Le guide complet est dans le fichier `README.md` du dossier.
>
> Cordialement,

---

## Support et évolutions

- Les données restent sur le poste du client ; sauvegardez régulièrement le dossier `data/` si la base est importante.
- Pour une mise à jour de l’outil : remplacer les fichiers `src/`, `app.py`, `requirements.txt` et les scripts `Demarrer.*`, en **conservant** `data/hotel_group_archive.db` si vous ne souhaitez pas réimporter.
- En cas de problème, noter le message d’erreur affiché dans le terminal ou dans l’interface avant de contacter le support.

---

## Pour le développement

Prérequis : Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### Ingestion en ligne de commande

```bash
PYTHONPATH=. python3 -m src.ingestion.cli ExportNF525_HotelCezanne_FR005082.zip
```

Plusieurs fichiers, sans ignorer les jours déjà couverts par un export mensuel :

```bash
PYTHONPATH=. python3 -m src.ingestion.cli ExportNF525_*.zip --no-skip-covered
```

### Lancer l’interface sans les scripts

```bash
PYTHONPATH=. python3 -m streamlit run app.py
```

### Tests

```bash
PYTHONPATH=. python3 -m pytest -q
```
