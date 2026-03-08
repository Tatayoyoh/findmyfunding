FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY src/ src/
COPY scripts/ scripts/
COPY data/ data/

# Import Excel data into SQLite at build time
RUN uv run python scripts/import_excel.py

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "findmyfundings.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
