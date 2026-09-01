"""Dashboard summary and alert API routes."""

import logging
from fastapi import APIRouter, HTTPException
from server.config import get_workspace_client
from server.jobs import list_jobs, bulk_runs_by_job
from server.anomaly import detect_anomalies_for_job
from server.alerts import get_alert_status, get_active_alerts, send_test_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


def _compute_summary_from_jobs(jobs, runs_map):
    """Compute summary stats from a list of JobInfo and a runs map."""
    total_jobs = len(jobs)
    running_count = sum(1 for j in jobs if j.get("status") == "RUNNING") if isinstance(jobs[0], dict) else sum(1 for j in jobs if j.status == "RUNNING")
    failed_count  = sum(1 for j in jobs if (j.get("status") if isinstance(j, dict) else j.status) == "FAILED")
    success_count = sum(1 for j in jobs if (j.get("status") if isinstance(j, dict) else j.status) == "SUCCESS")
    pending_count = sum(1 for j in jobs if (j.get("status") if isinstance(j, dict) else j.status) == "PENDING")
    return total_jobs, running_count, failed_count, success_count, pending_count


@router.get("/dashboard/summary")
async def get_dashboard_summary():
    """Get aggregated dashboard statistics.

    Reads from Lakebase cache when available (fast path).
    Falls back to live Databricks API if cache is empty or unavailable.
    """
    from server.db import is_configured, get_jobs_from_db, get_all_runs_from_db, is_cache_fresh

    try:
        # ── Fast path: serve from Lakebase cache ──────────────────────────────
        if is_configured():
            # Use the default workspace for the main dashboard
            from server.config import get_workspace_host
            try:
                host = get_workspace_host()
                workspace_id = host.replace("https://", "").split(".")[0]
            except Exception:
                workspace_id = None

            cached_jobs = await get_jobs_from_db(workspace_id)
            if cached_jobs and (workspace_id is None or await is_cache_fresh(workspace_id)):
                # Compute anomaly count from cached runs
                cached_runs_map = await get_all_runs_from_db(workspace_id, runs_per_job=10)

                total_jobs    = len(cached_jobs)
                running_count = sum(1 for j in cached_jobs if j.get("status") == "RUNNING")
                failed_count  = sum(1 for j in cached_jobs if j.get("status") == "FAILED")
                success_count = sum(1 for j in cached_jobs if j.get("status") == "SUCCESS")
                pending_count = sum(1 for j in cached_jobs if j.get("status") == "PENDING")

                # Reconstruct minimal JobInfo-like objects for anomaly detection
                from server.anomaly import detect_anomalies_for_job
                from server.jobs import JobInfo, JobRun
                from datetime import datetime

                anomaly_count = 0
                for jd in cached_jobs:
                    try:
                        lr_data = jd.get("latest_run")
                        latest_run = None
                        if lr_data and isinstance(lr_data, dict):
                            latest_run = JobRun(**{
                                k: v for k, v in lr_data.items()
                                if k in JobRun.model_fields
                            })
                        job_info = JobInfo(
                            job_id=jd["job_id"],
                            name=jd.get("name", ""),
                            status=jd.get("status", "UNKNOWN"),
                            latest_run=latest_run,
                        )
                        runs_for_job = cached_runs_map.get(jd["job_id"], [])
                        job_runs = [
                            JobRun(**{k: v for k, v in r.items() if k in JobRun.model_fields})
                            for r in runs_for_job
                            if isinstance(r, dict)
                        ]
                        anomalies = detect_anomalies_for_job(job_info, job_runs)
                        anomaly_count += len(anomalies)
                    except Exception as e:
                        logger.debug(f"Anomaly detection skipped for cached job: {e}")

                return {
                    "total_jobs": total_jobs,
                    "running": running_count,
                    "failed": failed_count,
                    "success": success_count,
                    "pending": pending_count,
                    "anomaly_count": anomaly_count,
                    "data_source": "cache",
                }

        # ── Slow path: live Databricks API ────────────────────────────────────
        w = get_workspace_client()
        jobs = list_jobs(w)

        total_jobs    = len(jobs)
        running_count = sum(1 for j in jobs if j.status == "RUNNING")
        failed_count  = sum(1 for j in jobs if j.status == "FAILED")
        success_count = sum(1 for j in jobs if j.status == "SUCCESS")
        pending_count = sum(1 for j in jobs if j.status == "PENDING")

        job_ids  = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(w, job_ids, runs_per_job=10)
        anomaly_count = 0
        for job_info in jobs:
            try:
                anomalies = detect_anomalies_for_job(job_info, runs_map.get(job_info.job_id, []))
                anomaly_count += len(anomalies)
            except Exception as e:
                logger.warning(f"Anomaly detection failed for job {job_info.job_id}: {e}")

        return {
            "total_jobs": total_jobs,
            "running": running_count,
            "failed": failed_count,
            "success": success_count,
            "pending": pending_count,
            "anomaly_count": anomaly_count,
            "data_source": "live",
        }

    except Exception as e:
        logger.error(f"Error in get_dashboard_summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/config")
def get_alerts_config():
    """Return alert configuration status (no passwords exposed)."""
    return get_alert_status()


@router.get("/alerts/active")
def get_alerts_active():
    """Return currently active (deduplicated) alerts."""
    return {"alerts": get_active_alerts()}


@router.post("/alerts/test")
def post_alerts_test():
    """Send a test email to configured recipients."""
    result = send_test_email()
    if result.get("success"):
        return result
    raise HTTPException(status_code=400, detail=result.get("error", "Failed to send test email"))
