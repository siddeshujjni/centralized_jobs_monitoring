"""AI-powered analysis endpoints using Databricks Foundation Model API."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from server.config import get_workspace_client, AI_ANALYSIS_ENABLED
from server.workspaces import get_workspace_client_for
from server.jobs import list_jobs, get_job_runs, compute_job_stats
from server.anomaly import detect_anomalies_for_job
from server.ai_analysis import analyze_job, analyze_workspace, JobAIInsight, WorkspaceAIInsight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _ensure_ai_enabled() -> None:
    """Guard: reject AI requests when the optional AI feature is disabled.

    AI analysis is off by default; set ENABLE_AI_ANALYSIS=true to turn it on.
    This is a backend safeguard in addition to the UI hiding the AI panels.
    """
    if not AI_ANALYSIS_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="AI analysis is disabled. Set ENABLE_AI_ANALYSIS=true to enable it.",
        )


@router.get("/jobs/{job_id}/analyze", response_model=JobAIInsight)
async def get_job_ai_analysis(job_id: int, workspace_id: Optional[str] = Query(None)):
    """
    AI-powered health analysis for a specific job.

    Uses Claude (Databricks Foundation Model API) to analyse run history,
    statistics, and detected anomalies, then returns a structured insight
    including health score, root cause analysis, and recommendations.
    """
    _ensure_ai_enabled()
    try:
        w = get_workspace_client_for(workspace_id) if workspace_id else get_workspace_client()

        # Gather all data the AI needs
        jobs = list_jobs(w)
        job_info = next((j for j in jobs if j.job_id == job_id), None)
        if not job_info:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        runs = get_job_runs(w, job_id, limit=20)
        stats = compute_job_stats(job_info.name, job_id, runs)
        anomalies = detect_anomalies_for_job(job_info, runs)

        insight = await analyze_job(job_info, runs, stats, anomalies, workspace_id=workspace_id or "")
        return insight

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI analysis failed for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.get("/workspace/analyze", response_model=WorkspaceAIInsight)
async def get_workspace_ai_analysis():
    """
    AI-powered workspace-level health summary.

    Aggregates all job statuses and anomalies, then asks Claude for a
    high-level assessment, top risks, and prioritised recommendations.
    """
    _ensure_ai_enabled()
    try:
        w = get_workspace_client()
        jobs = list_jobs(w)
        all_anomalies = []

        for job_info in jobs:
            try:
                runs = get_job_runs(w, job_info.job_id, limit=20)
                anomalies = detect_anomalies_for_job(job_info, runs)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.warning(f"Skipping job {job_info.job_id} during workspace analysis: {e}")

        insight = await analyze_workspace(jobs, all_anomalies)
        return insight

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace AI analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Workspace AI analysis failed: {str(e)}")
