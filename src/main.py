"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.database import init_db
from src.routers import search, programs, admin, api
from src.services.scheduler import start_scheduler, stop_scheduler


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

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates_dir = Path(__file__).parent / "templates"
app.state.templates = Jinja2Templates(directory=str(templates_dir))
app.state.templates.env.globals["today"] = date.today

# Routers
app.include_router(search.router)
app.include_router(programs.router)
app.include_router(admin.router)
app.include_router(api.router)
