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
uv run fastapi dev
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

## CSS compilation

```bash
curl -sSL https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 -o tools/tailwindcss
chmod +x tools/tailwindcss
# https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 -> tools/tailwindcss
./tools/tailwindcss -i src/static/css/input.css -o src/static/css/app.css --minify
# Ajouter --watch pendant le dev pour recompiler à la volée
```

## Production

```bash
# Pour avoir les source de build docker compose de Firecrawl
git clone https://github.com/firecrawl/firecrawl.git

ln -s docker-compose.prod.yml docker-compose.yml
docker-compose up -d
```