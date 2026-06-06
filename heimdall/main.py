from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from heimdall.api.routes import router
from heimdall.config import get_settings
from heimdall.db.session import init_db
from heimdall.logging_config import setup_logging

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(level=settings.log_level, json_logs=settings.json_logs)
    await init_db()
    yield


app = FastAPI(
    title="Heimdall",
    description=(
        "Ingest polarizing narratives, score outrage escalation, and map propagation "
        "graphs to detect coordinated inauthentic amplification."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
_cors = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")

if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
