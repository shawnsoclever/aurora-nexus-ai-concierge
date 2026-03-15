from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pathlib import Path

from core.llm import configure_runtime_environment
from observability.logging_config import configure_logging

configure_runtime_environment()
configure_logging()

from api.routes import router

app = FastAPI(title="Agentic Hotel Backend", version="0.1.0")
app.include_router(router)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/support")
def support_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "support.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
