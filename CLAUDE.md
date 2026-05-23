# FindMyFundings

Application web pour aider les structures (associations, ONG, coopératives, etc.) à trouver des financements auxquels elles ont accès.

## Stack technique

- **Backend** : Python 3.12+ / FastAPI / SQLite (FTS5) / Jinja2
- **Frontend** : HTMX + Tailwind CSS (CDN) + Lucide icons (CDN)
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
- **Icônes UI** : utiliser Lucide via `<i data-lucide="nom" class="w-N h-N"></i>`. Jamais de SVG inline manuel. Catalogue : https://lucide.dev/icons/
- **Maintenance de ce fichier** : après toute évolution structurelle (nouveau modèle de données, refonte d'un router, changement de stack, nouvelle convention UI), mettre à jour CLAUDE.md sans attendre que l'utilisateur le demande

## Modèle de données

Une seule table métier : `funding_programs`. Les URLs sources sont stockées **inline** dans la colonne `source_urls` (JSON list de `SourceLink`) :

```json
[{"url": "...", "label": "...", "last_hash": "...", "last_checked_at": "...", "has_changed": false}]
```

Champs scraping (`last_hash`, `last_checked_at`, `has_changed`) populés par le scheduler à chaque run. La table `monitored_sources` n'existe plus (fusionnée dans `source_urls`). Migration auto au startup via `database.py:_migrate_monitored_sources`.

`scraper.scrape_all()` itère les programmes, fetch chaque URL, compare le hash, met à jour le JSON inline. Si ≥1 URL change → contenu fusionné renvoyé pour ré-extraction IA via `ai_extractor`.

## Pages admin

- `/admin` : landing avec 2 cards (Gérer programmes / Exporter données + modal export)
- `/admin/programs` : 3 action cards (Ajouter source / Import Excel / Scraping manuel) + filtres toggle (Scraping, Expirés) + liste programmes avec sous-lignes "scraping" par URL (chip + dernier check + statut Modifié/OK/En attente)

## Données source

Le fichier `data/Cartographie des financements.xlsx` contient ~60 programmes de financement répartis en 6 catégories :
- Financements européens
- Financements publiques (État Français)
- BPI France
- Plateformes de crowdfunding
- Mécénat privé et fondations
- Acteurs de l'aide Social

Le fichier utilise des cellules fusionnées pour les catégories et certains programmes multi-lignes.
