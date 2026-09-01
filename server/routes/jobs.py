"""Job-related API routes."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from server.config import get_workspace_client
from server.workspaces import get_workspace_client_for
from server.jobs import list_jobs, get_job_runs, compute_job_stats, bulk_runs_by_job
from server.anomaly import detect_anomalies_for_job, Anomaly

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])


def _get_client(workspace_id: Optional[str]):
    """Return the right WorkspaceClient — workspace-specific or default."""
    if workspace_id:
        return get_workspace_client_for(workspace_id)
    return get_workspace_client()


@router.get("/jobs")
def get_jobs(workspace_id: Optional[str] = Query(None)):
    """List all jobs with latest run status."""
    try:
        w = _get_client(workspace_id)
        jobs = list_jobs(w)
        return {"jobs": [j.model_dump() for j in jobs]}
    except Exception as e:
        logger.error(f"Error in get_jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/runs")
def get_runs(job_id: int, workspace_id: Optional[str] = Query(None)):
    """Get run history for a specific job."""
    try:
        w = _get_client(workspace_id)
        runs = get_job_runs(w, job_id, limit=50)
        return {"runs": [r.model_dump() for r in runs]}
    except Exception as e:
        logger.error(f"Error in get_runs for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/stats")
def get_stats(job_id: int, workspace_id: Optional[str] = Query(None)):
    """Get statistics for a specific job."""
    try:
        w = _get_client(workspace_id)
        jobs = list_jobs(w)
        job_info = next((j for j in jobs if j.job_id == job_id), None)
        job_name = job_info.name if job_info else f"Job {job_id}"
        runs = get_job_runs(w, job_id, limit=20)
        stats = compute_job_stats(job_name, job_id, runs)
        return stats.model_dump()
    except Exception as e:
        logger.error(f"Error in get_stats for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies")
def get_anomalies(workspace_id: Optional[str] = Query(None)):
    """Get anomalies across all jobs in a workspace."""
    try:
        w = _get_client(workspace_id)
        jobs = list_jobs(w)
        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(w, job_ids, runs_per_job=20)
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
    except Exception as e:
        logger.error(f"Error in get_anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))
