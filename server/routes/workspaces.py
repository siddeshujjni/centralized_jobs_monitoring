"""Multi-workspace API routes."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException

from server.workspaces import list_workspaces, get_workspace_client_for, WorkspaceInfo
from server.jobs import list_jobs, get_job_runs, bulk_runs_by_job
from server.anomaly import detect_anomalies_for_job, Anomaly

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces"])

# Shared executor for parallel workspace fetches
_executor = ThreadPoolExecutor(max_workers=10)


# ---------------------------------------------------------------------------
# Helpers that run in threads (blocking SDK calls)
# ---------------------------------------------------------------------------

def _fetch_workspace_jobs(ws: WorkspaceInfo) -> dict:
    """Fetch jobs for a single workspace. Returns dict with workspace metadata."""
    try:
        client = get_workspace_client_for(ws.workspace_id)
        jobs = list_jobs(client)
        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "workspace_url": ws.workspace_url,
            "environment": ws.environment,
            "jobs": [j.model_dump() for j in jobs],
            "error": None,
        }
    except Exception as e:
        logger.error(f"Error fetching jobs for workspace {ws.workspace_id}: {e}")
        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "workspace_url": ws.workspace_url,
            "environment": ws.environment,
            "jobs": [],
            "error": str(e),
        }


def _fetch_workspace_anomalies(ws: WorkspaceInfo) -> dict:
    """Fetch anomalies for a single workspace using bulk run scan (2 API calls total)."""
    try:
        client = get_workspace_client_for(ws.workspace_id)
        jobs = list_jobs(client)
        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(client, job_ids, runs_per_job=20)
        all_anomalies: list[Anomaly] = []

        for job_info in jobs:
            try:
                runs = runs_map.get(job_info.job_id, [])
                anomalies = detect_anomalies_for_job(job_info, runs)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.warning(f"Error detecting anomalies for job {job_info.job_id} in {ws.workspace_id}: {e}")

        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "workspace_url": ws.workspace_url,
            "environment": ws.environment,
            "anomalies": [a.model_dump() for a in all_anomalies],
            "error": None,
        }
    except Exception as e:
        logger.error(f"Error fetching anomalies for workspace {ws.workspace_id}: {e}")
        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "workspace_url": ws.workspace_url,
            "environment": ws.environment,
            "anomalies": [],
            "error": str(e),
        }


def _fetch_workspace_summary(ws: WorkspaceInfo) -> dict:
    """Fetch summary stats for a single workspace using bulk run scan (2 API calls total)."""
    try:
        client = get_workspace_client_for(ws.workspace_id)
        jobs = list_jobs(client)

        total_jobs = len(jobs)
        running = sum(1 for j in jobs if j.status == "RUNNING")
        failed = sum(1 for j in jobs if j.status == "FAILED")
        success = sum(1 for j in jobs if j.status == "SUCCESS")

        # Count anomalies using bulk run scan instead of N individual calls
        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(client, job_ids, runs_per_job=20)
        anomaly_count = 0
        for job_info in jobs:
            try:
                runs = runs_map.get(job_info.job_id, [])
                anomalies = detect_anomalies_for_job(job_info, runs)
                anomaly_count += len(anomalies)
            except Exception as e:
                logger.warning(f"Error detecting anomalies for job {job_info.job_id} in {ws.workspace_id}: {e}")

        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "environment": ws.environment,
            "total_jobs": total_jobs,
            "running": running,
            "failed": failed,
            "success": success,
            "anomaly_count": anomaly_count,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Error fetching summary for workspace {ws.workspace_id}: {e}")
        return {
            "workspace_id": ws.workspace_id,
            "workspace_name": ws.workspace_name,
            "environment": ws.environment,
            "total_jobs": 0,
            "running": 0,
            "failed": 0,
            "success": 0,
            "anomaly_count": 0,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Single-workspace routes
# ---------------------------------------------------------------------------

@router.get("/api/workspaces")
def get_workspaces():
    """List all discovered workspaces."""
    try:
        workspaces = list_workspaces()
        return {"workspaces": [w.model_dump() for w in workspaces]}
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspaces/{workspace_id}/jobs")
def get_workspace_jobs(workspace_id: str):
    """Get jobs for a specific workspace."""
    try:
        client = get_workspace_client_for(workspace_id)
        jobs = list_jobs(client)
        return {"jobs": [j.model_dump() for j in jobs]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching jobs for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspaces/{workspace_id}/anomalies")
def get_workspace_anomalies(workspace_id: str):
    """Get anomalies for a specific workspace."""
    try:
        client = get_workspace_client_for(workspace_id)
        jobs = list_jobs(client)
        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(client, job_ids, runs_per_job=20)
        all_anomalies: list[Anomaly] = []

        for job_info in jobs:
            try:
                runs = runs_map.get(job_info.job_id, [])
                anomalies = detect_anomalies_for_job(job_info, runs)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.warning(f"Error detecting anomalies for job {job_info.job_id}: {e}")

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_anomalies.sort(key=lambda a: severity_order.get(a.severity, 99))

        return {"anomalies": [a.model_dump() for a in all_anomalies]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching anomalies for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspaces/{workspace_id}/summary")
def get_workspace_summary(workspace_id: str):
    """Get summary stats for a specific workspace."""
    try:
        client = get_workspace_client_for(workspace_id)
        jobs = list_jobs(client)

        total_jobs = len(jobs)
        running = sum(1 for j in jobs if j.status == "RUNNING")
        failed = sum(1 for j in jobs if j.status == "FAILED")
        success = sum(1 for j in jobs if j.status == "SUCCESS")
        pending = sum(1 for j in jobs if j.status == "PENDING")

        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(client, job_ids, runs_per_job=20)
        anomaly_count = 0
        for job_info in jobs:
            try:
                runs = runs_map.get(job_info.job_id, [])
                anomalies = detect_anomalies_for_job(job_info, runs)
                anomaly_count += len(anomalies)
            except Exception as e:
                logger.warning(f"Error detecting anomalies for job {job_info.job_id}: {e}")

        return {
            "total_jobs": total_jobs,
            "running": running,
            "failed": failed,
            "success": success,
            "pending": pending,
            "anomaly_count": anomaly_count,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching summary for workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Multi-workspace (aggregated) routes
# ---------------------------------------------------------------------------

@router.get("/api/multi/summary")
async def get_multi_summary():
    """Aggregated summary across all workspaces. Fetches in parallel."""
    workspaces = list_workspaces()
    if not workspaces:
        return {
            "workspaces": [],
            "totals": {"total_jobs": 0, "running": 0, "failed": 0, "anomaly_count": 0},
        }

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, _fetch_workspace_summary, ws) for ws in workspaces]
    results = await asyncio.gather(*tasks)

    totals = {
        "total_jobs": sum(r["total_jobs"] for r in results),
        "running": sum(r["running"] for r in results),
        "failed": sum(r["failed"] for r in results),
        "anomaly_count": sum(r["anomaly_count"] for r in results),
    }

    return {"workspaces": results, "totals": totals}


@router.get("/api/multi/anomalies")
async def get_multi_anomalies():
    """All anomalies across all workspaces, sorted by severity."""
    workspaces = list_workspaces()
    if not workspaces:
        return {"anomalies": []}

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, _fetch_workspace_anomalies, ws) for ws in workspaces]
    results = await asyncio.gather(*tasks)

    # Flatten and tag anomalies with workspace info
    all_anomalies = []
    for result in results:
        for anomaly in result["anomalies"]:
            anomaly["workspace_id"] = result["workspace_id"]
            anomaly["workspace_name"] = result["workspace_name"]
            anomaly["workspace_url"] = result["workspace_url"]
            anomaly["environment"] = result["environment"]
            all_anomalies.append(anomaly)

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_anomalies.sort(key=lambda a: severity_order.get(a.get("severity", ""), 99))

    return {"anomalies": all_anomalies}


@router.get("/api/multi/jobs")
async def get_multi_jobs():
    """All jobs across all workspaces with workspace metadata.

    Reads from Lakebase cache when fresh; falls back to live parallel fetch.
    """
    from server.db import is_configured, get_jobs_from_db, is_cache_fresh

    workspaces = list_workspaces()
    if not workspaces:
        return {"jobs": [], "data_source": "live"}

    # ── Fast path: serve from Lakebase ────────────────────────────────────────
    if is_configured():
        all_fresh = all(
            await asyncio.gather(*[is_cache_fresh(ws.workspace_id) for ws in workspaces])
        )
        if all_fresh:
            cached = await get_jobs_from_db()  # all workspaces
            if cached:
                # Build workspace lookup for enrichment
                ws_map = {
                    ws.workspace_id: ws for ws in workspaces
                }
                all_jobs = []
                for job in cached:
                    ws = ws_map.get(job.get("workspace_id"))
                    if ws:
                        job["workspace_name"] = ws.workspace_name
                        job["workspace_url"] = ws.workspace_url
                        job["environment"] = ws.environment
                    all_jobs.append(job)
                return {"jobs": all_jobs, "data_source": "cache"}

    # ── Slow path: live parallel API fetch ────────────────────────────────────
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, _fetch_workspace_jobs, ws) for ws in workspaces]
    results = await asyncio.gather(*tasks)

    all_jobs = []
    for result in results:
        for job in result["jobs"]:
            job["workspace_id"] = result["workspace_id"]
            job["workspace_name"] = result["workspace_name"]
            job["workspace_url"] = result["workspace_url"]
            job["environment"] = result["environment"]
            all_jobs.append(job)

    return {"jobs": all_jobs, "data_source": "live"}
