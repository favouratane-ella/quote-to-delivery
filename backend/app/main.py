"""FastAPI entry point. Serves the API under /api and the built React app at /."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .api_recovery import router as recovery_router
from .config import settings
from .db import SessionLocal, init_db
from .seed import ensure_main_world


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.SEED_ON_START:
        db = SessionLocal()
        try:
            ensure_main_world(db)
        finally:
            db.close()
    yield


app = FastAPI(title="Quote-to-Delivery Accelerator", version="1.0.0", lifespan=lifespan)
if settings.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(recovery_router)

dist = settings.FRONTEND_DIST
if (dist / "index.html").exists():
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"app": "Quote-to-Delivery Accelerator API", "docs": "/docs", "note": "Build the frontend (cd frontend && npm run build) to serve the UI here."}
