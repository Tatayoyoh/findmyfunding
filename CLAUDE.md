# FindMyFundings

Application web pour aider les structures (associations, ONG, coopératives, etc.) à trouver des financements auxquels elles ont accès.

## Stack technique

- **Backend** : Python 3.12+ / FastAPI / SQLite (FTS5) / Jinja2
- **Frontend** : HTMX + Tailwind CSS (CDN) + Lucide icons (CDN)
- **Scraping + extraction** : Firecrawl self-hébergé (intégré au `docker-compose.prod.yml` comme services `firecrawl-*`, port 3002) → endpoint `/extract` avec schéma Pydantic. Voir `firecrawl/README.md` pour le setup.
- **LLM** : DeepSeek (`deepseek-chat`) via API OpenAI-compatible. Utilisé par Firecrawl (extraction structurée) et par `excel_import.py` (parse dates de soumission)
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
│   ├── scraper.py       # Firecrawl extract → FundingExtraction (Pydantic schema)
│   └── scheduler.py     # APScheduler mensuel → scrape_all()
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

Champs `last_checked_at` populés par le scraper à chaque run (Firecrawl ne donne pas de hash natif). La table `monitored_sources` n'existe plus (fusionnée dans `source_urls`). Migration auto au startup via `database.py:_migrate_monitored_sources`.

Colonnes JSON additionnelles sur `funding_programs` (extraction Firecrawl) : `summary`, `eligibility_criteria`, `fundable_axes`, `relevant_links`, `pdf_documents`, `tags`. Migration `_migrate_firecrawl_columns` ajoute les colonnes manquantes au startup.

`scraper.scrape_all()` itère les programmes, passe toutes leurs URLs à `Firecrawl.extract()` avec le schéma `FundingExtraction` (Pydantic), puis persiste les champs structurés en DB. Pas de change-detection par hash dans cette version — re-extraction complète à chaque scrape (coût DeepSeek négligeable, ~30c pour 60 progs).

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
