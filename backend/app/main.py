from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import get_settings
from app.routers import predictions as predictions_router

settings = get_settings()

app = FastAPI(
    title="SesliTahmin API",
    version=__version__,
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
