import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import alerts, announcements, copilot, portfolio, research, system
from .config import settings
from .database import SessionLocal, init_db
from .services import demo_seed
from .services.state import is_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("finn")
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


async def _refresh_loop():
    """Optional lightweight scheduler (REFRESH_INTERVAL_MIN>0): live mode only; every job is idempotent."""
    from .api.system import refresh_live
    while True:
        await asyncio.sleep(settings.refresh_interval_min * 60)
        db = SessionLocal()
        try:
            if not is_demo(db):
                await asyncio.to_thread(refresh_live, db)
        except Exception as e:
            log.warning("scheduled refresh failed: %s", e)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        demo_seed.ensure_seeded(db)
    finally:
        db.close()
    task = asyncio.create_task(_refresh_loop()) if settings.refresh_interval_min > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="FINN – Financial Investment Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
for r in (system.router, portfolio.router, announcements.router, alerts.router, research.router, copilot.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal error – see server logs."})


if FRONTEND_DIST.exists():  # single-origin deployment: serve the built SPA from the API process
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        f = FRONTEND_DIST / full_path
        return FileResponse(f if f.is_file() else FRONTEND_DIST / "index.html")
