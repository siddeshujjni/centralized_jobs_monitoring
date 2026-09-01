"""Databricks Jobs Monitor & Anomaly Detection App."""

import os
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from server.config import AI_ANALYSIS_ENABLED
from server.routes.jobs import router as jobs_router
from server.routes.dashboard import router as dashboard_router
from server.routes.ai import router as ai_router
from server.routes.workspaces import router as workspaces_router
from server.routes.setup import router as setup_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_COMPANY_NAME = os.environ.get("APP_COMPANY_NAME", "Databricks")
APP_NAME = f"{APP_COMPANY_NAME} Jobs Monitor"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"{APP_NAME} starting up...")
    tasks = []

    # Start Lakebase background poller if configured
    from server.db import is_configured as lakebase_configured
    if lakebase_configured():
        from server.poller import start_poller
        tasks.append(asyncio.create_task(start_poller()))
        logger.info("Lakebase cache poller started")
    else:
        logger.info("Lakebase not configured — running without cache (set PGHOST to enable)")

    # Start background alert polling if email is configured
    if os.environ.get("ALERT_EMAIL_TO"):
        from server.alerts import start_alert_loop
        tasks.append(asyncio.create_task(start_alert_loop()))
        logger.info("Email alert engine started")

    if AI_ANALYSIS_ENABLED:
        logger.info("AI analysis ENABLED (ENABLE_AI_ANALYSIS=true)")
    else:
        logger.info("AI analysis disabled — set ENABLE_AI_ANALYSIS=true to enable")

    yield

    for task in tasks:
        task.cancel()
    logger.info(f"{APP_NAME} shutting down...")


app = FastAPI(
    title="Databricks Jobs Monitor",
    description="Real-time Databricks Jobs monitoring with AI-powered anomaly detection",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(jobs_router)
app.include_router(dashboard_router)
app.include_router(ai_router)
app.include_router(workspaces_router)
app.include_router(setup_router)


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": "databricks-jobs-monitor", "version": "2.0.0"}


@app.get("/api/config")
def app_config():
    """Frontend configuration — safe, non-sensitive values only."""
    from server.db import is_configured as lakebase_configured
    return {
        "company_name": APP_COMPANY_NAME,
        "app_name": APP_NAME,
        "lakebase_enabled": lakebase_configured(),
        "ai_enabled": AI_ANALYSIS_ENABLED,
    }


@app.get("/api/cache/status")
async def cache_status():
    """Lakebase cache sync status per workspace."""
    from server.db import get_sync_status, is_configured as lakebase_configured
    if not lakebase_configured():
        return {"enabled": False, "message": "Lakebase not configured (PGHOST not set)", "workspaces": []}
    statuses = await get_sync_status()
    # Convert datetime objects to ISO strings for JSON
    for s in statuses:
        if s.get("last_synced_at"):
            s["last_synced_at"] = s["last_synced_at"].isoformat()
    return {"enabled": True, "workspaces": statuses}


# Serve React frontend
frontend_dist = Path(__file__).parent / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve SPA for API routes
        if full_path.startswith("api/"):
            return {"error": "Not found"}
        # Serve static files if they exist
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/")
    def root():
        return {
            "message": "Databricks Jobs Monitor API",
            "docs": "/docs",
            "note": "Frontend not built. Run: cd frontend && npm install && npm run build",
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
