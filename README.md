# Ocirisation et Parsing des Documents Maritimes

Pipeline complet d'océrisation (OCR), de parsing structurel, de stockage, de génération d'alertes réglementaires et de supervision pour les documents maritimes traités par une autorité portuaire — projet de fin d'Anne  réalisé dans le contexte de Tanger Med Port Authority.

Trois familles de documents sont couvertes :
- **Health** — Maritime Declaration of Health (déclaration maritime de santé)
- **DGM** — Dangerous Cargo Manifest (manifeste de cargaison dangereuse)
- **DGD** — Dangerous Cargo Declaration (déclaration de cargaison dangereuse)

## Sommaire

- [Architecture](#architecture)
- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Structure du dépôt](#structure-du-dépôt)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Schéma de base de données](#schéma-de-base-de-données)
- [Règles d'alerte](#règles-dalerte)
- [Points d'accès API](#points-daccès-api)
- [Limitations connues](#limitations-connues)

## Architecture

```
PDF scanné → Conversion en image → Prétraitement → OCR (PaddleOCR)
    → Extraction spatiale (parsing par ancrage de libellés) → JSON structuré
    → Base de données (PostgreSQL) → Moteur d'alertes → API (FastAPI)
    → Tableau de bord de supervision (React)
```

Le parsing repose sur une approche déterministe par **coordonnées de positionnement (boîtes englobantes)** plutôt que sur un modèle de langage — des essais avec des LLM légers (Qwen2.5:3b, Phi) servis localement via Ollama ont montré un temps de traitement bien supérieur et une extraction de champs insuffisamment fiable sur les tableaux denses, ce qui a motivé ce choix.

## Fonctionnalités

- Océrisation et extraction structurée des 3 familles de documents, avec gestion des documents multi-pages, des variations de mise en page, des cases à cocher barrées, et des réimpressions de formulaire
- Stockage en base PostgreSQL avec conservation du JSON brut pour traçabilité
- Génération automatique d'alertes à l'ingestion (cargo de classe critique, réponse sanitaire positive, certificat expiré, document obsolète), avec déduplication déterministe
- API REST (FastAPI) : upload PDF avec océrisation à la volée, upload JSON direct, consultation documents/alertes, statistiques agrégées
- Tableau de bord React : vue d'ensemble avec graphiques, import de documents, liste des documents, journal des alertes, historique des traitements
- Thème clair/sombre, menu latéral repliable

## Stack technique

| Domaine | Technologies |
|---|---|
| OCR | PaddleOCR |
| Traitement d'image | OpenCV |
| Conversion PDF | pypdfium2 |
| Backend / API | Python, FastAPI, SQLAlchemy |
| Base de données | PostgreSQL |
| Frontend | React, Vite, Recharts |
| Essais LLM (écartés) | Ollama (Qwen2.5:3b, Phi) |

## Structure du dépôt

```
prjt_OCR_maritime/
├── src/                        # Pipeline OCR et parsing
│   ├── field_extractor.py      # Extraction des champs Health
│   ├── dgd_extractor.py        # Extraction DGD (en-tête)
│   ├── dgd_table_extractor.py  # Extraction DGD (grille classe/division)
│   ├── dgm_extractor.py        # Extraction DGM (en-tête)
│   ├── dgm_table_extractor.py  # Extraction DGM (tableau marchandises)
│   ├── image_preprocessing.py
│   ├── ocr_engine.py
│   ├── pdf_converter.py
│   ├── json_exporter.py
│   ├── main.py                 # Pipeline Health
│   ├── main_dgm.py              # Pipeline DGM
│   └── main_dgd.py              # Pipeline DGD
│
├── backend/                    # API + base de données + moteur d'alertes
│   ├── schema.sql               # Schéma PostgreSQL (source de vérité)
│   ├── models.py                 # Modèles SQLAlchemy
│   ├── database.py               # Connexion + init DB
│   ├── date_utils.py             # Parsing de dates hétérogènes
│   ├── ingest.py                  # Ingestion JSON → PostgreSQL
│   ├── alert_engine.py            # Règles de génération d'alertes
│   ├── ocr_bridge.py              # Pont API ↔ pipeline OCR (src/)
│   ├── api.py                     # Endpoints FastAPI
│   └── requirements.txt
│
├── frontend/                   # Tableau de bord de supervision
│   ├── src/
│   │   ├── pages/                # Dashboard, Import, Documents, Alertes, Historique
│   │   ├── components/           # Graphiques, tableaux, layout
│   │   └── hooks/                 # useDashboardData, useTheme, useSidebar
│   └── package.json
│
├── output/                     # JSON extraits par le pipeline OCR (généré)
├── rapport/                    # Rapport de stage (LaTeX)
└── README.md
```

## Installation

### Prérequis
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+

### 1. Base de données

```powershell
psql -U postgres -c "CREATE DATABASE maritime_docs;"
```

### 2. Backend

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure la connexion (variables d'environnement, ou fichier `.env` — voir `.env.example`) :

```powershell
$env:PFA_DB_HOST="localhost"
$env:PFA_DB_PORT="5432"
$env:PFA_DB_NAME="maritime_docs"
$env:PFA_DB_USER="postgres"
$env:PFA_DB_PASSWORD="ton_mot_de_passe"
```

Crée les tables :

```powershell
python database.py
```

### 3. Environnement OCR

Le pipeline dans `src/` dépend de PaddleOCR, OpenCV et pypdfium2. Installe-les dans le même environnement que le backend (`venv`), ou dans un environnement dédié :

```powershell
pip install paddleocr paddlepaddle opencv-python pypdfium2 numpy
```

### 4. Frontend

```powershell
cd frontend
npm install
```

## Utilisation

### Lancer l'API

```powershell
cd backend
venv\Scripts\Activate.ps1
uvicorn api:app --reload --port 8000
```

Documentation interactive : http://localhost:8000/docs

### Lancer le tableau de bord

```powershell
cd frontend
npm run dev
```

→ http://localhost:5173

### Ingérer des documents en ligne de commande

```powershell
cd backend
python ingest.py ..\output
```

### Océriser un document directement

```powershell
cd src
python main_dgd.py chemin\vers\document.pdf
python main_dgm.py chemin\vers\document.pdf
python main.py chemin\vers\document.pdf --doc-type Health
```

Ou depuis l'interface : onglet **Importer un document** → glisser un PDF.

## Schéma de base de données

10 tables : une table centrale `documents` (type, navire, JSON brut conservé pour traçabilité), des tables d'en-tête par type de document (`health_declarations`, `dgm_declarations`, `dgd_declarations`), des tables de détail (`health_questions`, `health_ports_of_call`, `health_crew_joined`, `dgm_cargo_items`, `dgd_matrix`), et une table `alerts` avec clé de déduplication (`dedup_key`) garantissant qu'une même condition détectée sur un document déjà traité ne génère jamais de doublon. Détail complet dans [`backend/schema.sql`](backend/schema.sql).

## Règles d'alerte

| Type | Condition |
|---|---|
| `DANGEROUS_CLASS` | Classe IMDG 1, 6.2 ou 7 renseignée avec une quantité/poids non nul (DGD ou DGM) |
| `HEALTH_POSITIVE` | Au moins une réponse positive au questionnaire sanitaire (q1-q9) |
| `CERTIFICATE_EXPIRED` | Certificat sanitaire dont la date de validité est dépassée |
| `DOCUMENT_OUTDATED` | Document dont la date de référence remonte à plus de 6 mois |

## Points d'accès API

| Endpoint | Fonction |
|---|---|
| `GET /documents` | Liste des documents, filtrable par type/navire |
| `GET /documents/{id}` | Détail d'un document, JSON brut et alertes |
| `GET /documents/{id}/class-breakdown` | Répartition en % des classes IMDG d'un document |
| `GET /alerts` | Liste des alertes, filtrable par type/statut |
| `PATCH /alerts/{id}/acknowledge` | Marque une alerte comme traitée |
| `GET /stats/summary` | Indicateurs agrégés (dashboard) |
| `GET /stats/dangerous-classes`, `/stats/all-classes`, `/stats/health-questions`, `/stats/alerts-timeline` | Données pour les graphiques |
| `GET /history` | Historique des documents, temps d'océrisation, alertes |
| `POST /ingest/upload-pdf` | Upload PDF → océrisation → ingestion |
| `POST /ingest/upload` | Upload direct d'un JSON déjà extrait |

## Limitations connues

- L'extraction DGM sur certains documents peut encore produire des lignes fantômes en fin de tableau ou mélanger deux lignes physiques adjacentes lorsque l'OCR manque un numéro de conteneur — un filet de sécurité (`_drop_exact_reprint_duplicates`) atténue les cas de doublon strict, mais ne couvre pas tous les cas observés (texte corrompu différemment à chaque répétition).
- Pas de réévaluation périodique automatisée des alertes déjà en base (une alerte `CERTIFICATE_EXPIRED` calculée hier ne se redéclenche pas seule aujourd'hui si le document n'est pas ré-ingéré).
- `ocr_bridge.py` localise `main_dgd.py`/`main_dgm.py`/`main.py` dynamiquement dans le projet ; si ces fichiers sont déplacés hors d'un sous-dossier de la racine (à côté direct de `src/`), l'import `from src.xxx` peut échouer.

## Auteur

Projet de fin d'année — Tanger Med Port Authority, 2025-2026.
