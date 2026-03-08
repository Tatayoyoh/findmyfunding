# FindMyFundings

Application web pour aider les structures (associations, ONG, coopératives, etc.) à trouver des financements auxquels elles ont accès.

## Stack technique

- **Backend** : Python 3.12+ / FastAPI / SQLite (FTS5) / Jinja2
- **Frontend** : HTMX + Tailwind CSS (CDN)
- **Scraping** : httpx + BeautifulSoup
- **Extraction IA** : Anthropic Claude API (claude-sonnet-4-20250514)
- **Scheduler** : APScheduler (scraping mensuel le 1er du mois à 3h)
- **Package manager** : `uv`

## Commandes

```bash
# Installer les dépendances
uv sync

# Importer le fichier Excel dans la base
uv run python scripts/import_excel.py

# Lancer le serveur de développement
uv run uvicorn findmyfundings.main:app --reload --app-dir src

# Lancer un scraping manuel
uv run python scripts/run_scrape.py

# Lancer les tests
uv run pytest tests/
```

## Structure du projet

```
src/findmyfundings/
├── main.py              # Entry point FastAPI + lifespan
├── config.py            # Settings (pydantic-settings, .env)
├── database.py          # SQLite connection, schema, FTS5
├── models.py            # Pydantic models
├── routers/
│   ├── search.py        # GET / (page principale) + GET /search (HTMX)
│   ├── programs.py      # GET /program/{id} (détail)
│   ├── admin.py         # Admin: import, sources, scraping
│   └── api.py           # JSON API (/api/programs, /api/search)
├── services/
│   ├── excel_import.py  # Parse Excel (cellules fusionnées, hyperlinks)
│   ├── funding_repo.py  # CRUD funding_programs
│   ├── search_service.py # Recherche FTS5 + filtres
│   ├── scraper.py       # Fetch + parse URLs
│   ├── ai_extractor.py  # Claude API extraction structurée
│   └── scheduler.py     # APScheduler mensuel
└── templates/           # Jinja2 + HTMX
```

## Conventions

- Langue du code : anglais (variables, fonctions, commentaires techniques)
- Langue de l'UI et des données : français
- Utiliser `uv run` pour toute exécution Python
- Base de données : `data/findmyfundings.db` (gitignored)
- Variables d'environnement dans `.env` (voir `.env.example`)
- Ne jamais committer de clés API ou de fichiers .env

## Données source

Le fichier `data/Cartographie des financements.xlsx` contient ~60 programmes de financement répartis en 6 catégories :
- Financements européens
- Financements publiques (État Français)
- BPI France
- Plateformes de crowdfunding
- Mécénat privé et fondations
- Acteurs de l'aide Social

Le fichier utilise des cellules fusionnées pour les catégories et certains programmes multi-lignes.
