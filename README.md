# Find my funding

Plateforme de faciliation d'accès aux fonds de financements

https://findmyfunding.rgdb.space

## Développement

Installer les dépendances
```bash
uv sync
```

Lancer le serveur de développement
```bash
uv run uvicorn findmyfundings.main:app --reload --app-dir src
```

Lancer les tests
```bash
uv run pytest tests/
```

Autres actions
```bash
# Importer le fichier Excel dans la base
uv run python scripts/import_excel.py

# Lancer un scraping manuel
uv run python scripts/run_scrape.py
```

## Production

```bash
# Pour avoir les source de build docker compose de Firecrawl
git clone https://github.com/firecrawl/firecrawl.git

ln -s docker-compose.prod.yml docker-compose.yml
docker-compose up -d
```