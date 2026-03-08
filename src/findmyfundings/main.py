"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from findmyfundings.database import init_db
from findmyfundings.routers import search, programs, admin, api
from findmyfundings.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="FindMyFundings",
    description="Cartographie des financements pour les structures",
    version="0.1.0",
    lifespan=lifespan,
)

# Templates
templates_dir = Path(__file__).parent / "templates"
app.state.templates = Jinja2Templates(directory=str(templates_dir))

# Routers
app.include_router(search.router)
app.include_router(programs.router)
app.include_router(admin.router)
app.include_router(api.router)
