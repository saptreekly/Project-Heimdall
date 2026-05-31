from contextlib import asynccontextmanager

from fastapi import FastAPI

from heimdall.api.routes import router
from heimdall.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(router, prefix="/api/v1")
