from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import get_settings
from app.routers import predictions as predictions_router
from app.services.prices import close_http_client
from app.services.llm import close_openai_client

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_http_client()
    await close_openai_client()


app = FastAPI(
    title="SesliTahmin API",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(predictions_router.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
