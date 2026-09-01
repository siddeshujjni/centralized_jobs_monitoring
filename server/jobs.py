"""Jobs data access layer - fetches jobs and runs from Databricks."""

import time
import logging
from datetime import datetime, timezone
from itertools import islice
from typing import Optional
from pydantic import BaseModel
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)


class JobRun(BaseModel):
    run_id: int
    job_id: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    state: str  # PENDING, RUNNING, TERMINATED, SKIPPED, INTERNAL_ERROR
    result_state: Optional[str] = None  # SUCCESS, FAILED, TIMEDOUT, CANCELED
    trigger: Optional[str] = None
    run_name: Optional[str] = None
    run_page_url: Optional[str] = None


class JobInfo(BaseModel):
    job_id: int
    name: str
    creator: Optional[str] = None
    created_time: Optional[datetime] = None
    schedule: Optional[str] = None
    latest_run: Optional[JobRun] = None
    status: str = "UNKNOWN"  # RUNNING, SUCCESS, FAILED, NO_RUNS


class JobStats(BaseModel):
    job_id: int
    job_name: str
    total_runs: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    p95_duration_seconds: float
    last_run_time: Optional[datetime] = None


def _epoch_ms_to_dt(ms: Optional[int]) -> Optional[datetime]:
    if ms is None or ms == 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _parse_run(run) -> JobRun:
    """Parse a Databricks SDK run object into our JobRun model."""
    state_str = "UNKNOWN"
    result_str = None

    if run.state:
        if run.state.life_cycle_state:
            state_str = run.state.life_cycle_state.value
        if run.state.result_state:
            result_str = run.state.result_state.value

    start = _epoch_ms_to_dt(run.start_time)
    end = _epoch_ms_to_dt(run.end_time)

    duration = None
    if run.run_duration is not None:
        duration = run.run_duration / 1000
    elif start and end:
        duration = (end - start).total_seconds()
    elif start and state_str == "RUNNING":
        duration = (datetime.now(timezone.utc) - start).total_seconds()

    trigger = None
    if run.trigger:
        trigger = str(run.trigger)

    return JobRun(
        run_id=run.run_id,
        job_id=run.job_id or 0,
        start_time=start,
        end_time=end,
        duration_seconds=duration,
        state=state_str,
        result_state=result_str,
        trigger=trigger,
        run_name=run.run_name,
        run_page_url=run.run_page_url,
    )


def _take(iterator, n: int) -> list:
    """Take at most n items from an iterator without materializing all pages."""
    return list(islice(iterator, n))


def bulk_runs_by_job(w: WorkspaceClient, job_ids: set, runs_per_job: int = 10, scan_limit: int = 2000) -> dict[int, list[JobRun]]:
    """Fetch up to `runs_per_job` recent runs for every job in a single paginated scan.

    Returns dict of job_id -> [JobRun, ...].  Replaces N individual list_runs(job_id=X)
    calls with one streaming scan — 1 API call instead of N.
    """
    job_runs: dict[int, list[JobRun]] = {jid: [] for jid in job_ids}
    scanned = 0
    try:
        for run in w.jobs.list_runs(active_only=False, completed_only=False):
            jid = run.job_id
            if jid in job_runs and len(job_runs[jid]) < runs_per_job:
                job_runs[jid].append(_parse_run(run))
            scanned += 1
            # Stop when every job has enough runs or we've scanned enough
            if scanned >= scan_limit:
                break
            if all(len(v) >= runs_per_job for v in job_runs.values()):
                break
    except Exception as e:
        logger.warning(f"Bulk runs scan failed: {e}")
    return job_runs


def _bulk_latest_runs(w: WorkspaceClient, job_ids: set, scan_limit: int = 1000) -> dict[int, JobRun]:
    """Fetch latest run per job using a single list_runs() call (no job_id filter).

    Returns a map of job_id -> latest JobRun. Much faster than N individual
    list_runs(job_id=...) calls — reduces N+1 queries to 2 API calls total.
    """
    job_run_map: dict[int, JobRun] = {}
    try:
        scanned = 0
        for run in w.jobs.list_runs(active_only=False, completed_only=False):
            jid = run.job_id
            if jid and jid in job_ids and jid not in job_run_map:
                job_run_map[jid] = _parse_run(run)
            scanned += 1
            # Stop early once we have a run for every job or hit the scan cap
            if len(job_run_map) >= len(job_ids) or scanned >= scan_limit:
                break
    except Exception as e:
        logger.warning(f"Bulk run fetch failed: {e}")
    return job_run_map


def _apply_run_status(job_info: "JobInfo", latest: JobRun) -> None:
    job_info.latest_run = latest
    if latest.state == "RUNNING":
        job_info.status = "RUNNING"
    elif latest.result_state == "SUCCESS":
        job_info.status = "SUCCESS"
    elif latest.result_state in ("FAILED", "TIMEDOUT"):
        job_info.status = "FAILED"
    elif latest.state == "PENDING":
        job_info.status = "PENDING"
    else:
        job_info.status = latest.result_state or latest.state


def list_jobs(w: WorkspaceClient, max_jobs: int = 500) -> list[JobInfo]:
    """List all jobs with their latest run status.

    Uses a bulk list_runs() call to avoid N+1 API requests.
    """
    jobs = []
    try:
        for job in islice(w.jobs.list(expand_tasks=False), max_jobs):
            schedule_str = None
            if job.settings and job.settings.schedule:
                schedule_str = job.settings.schedule.quartz_cron_expression

            creator = job.creator_user_name or None
            created = _epoch_ms_to_dt(job.created_time)

            jobs.append(JobInfo(
                job_id=job.job_id,
                name=job.settings.name if job.settings else f"Job {job.job_id}",
                creator=creator,
                created_time=created,
                schedule=schedule_str,
            ))
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        return []

    if not jobs:
        return jobs

    # Single bulk call to get latest run per job (2 API calls total, not N+1)
    job_ids = {j.job_id for j in jobs}
    job_run_map = _bulk_latest_runs(w, job_ids)

    for job_info in jobs:
        latest = job_run_map.get(job_info.job_id)
        if latest:
            _apply_run_status(job_info, latest)
        else:
            job_info.status = "NO_RUNS"

    return jobs


def get_job_runs(w: WorkspaceClient, job_id: int, limit: int = 50) -> list[JobRun]:
    """Get run history for a specific job."""
    try:
        runs = _take(w.jobs.list_runs(job_id=job_id, active_only=False, completed_only=False), limit)
        return [_parse_run(run) for run in runs]
    except Exception as e:
        logger.error(f"Error fetching runs for job {job_id}: {e}")
        return []


def compute_job_stats(job_name: str, job_id: int, runs: list[JobRun]) -> JobStats:
    """Compute statistics from a list of runs."""
    completed_runs = [r for r in runs if r.result_state in ("SUCCESS", "FAILED", "TIMEDOUT", "CANCELED")]
    success_runs = [r for r in completed_runs if r.result_state == "SUCCESS"]
    failed_runs = [r for r in completed_runs if r.result_state in ("FAILED", "TIMEDOUT")]

    durations = [r.duration_seconds for r in completed_runs if r.duration_seconds is not None and r.duration_seconds > 0]

    total = len(completed_runs)
    success_count = len(success_runs)
    failure_count = len(failed_runs)
    success_rate = (success_count / total * 100) if total > 0 else 0.0

    avg_dur = sum(durations) / len(durations) if durations else 0.0
    min_dur = min(durations) if durations else 0.0
    max_dur = max(durations) if durations else 0.0

    # P95
    if durations:
        sorted_d = sorted(durations)
        idx = int(len(sorted_d) * 0.95)
        idx = min(idx, len(sorted_d) - 1)
        p95 = sorted_d[idx]
    else:
        p95 = 0.0

    last_run_time = None
    if runs:
        last_run_time = runs[0].start_time

    return JobStats(
        job_id=job_id,
        job_name=job_name,
        total_runs=total,
        success_count=success_count,
        failure_count=failure_count,
        success_rate=round(success_rate, 1),
        avg_duration_seconds=round(avg_dur, 1),
        min_duration_seconds=round(min_dur, 1),
        max_duration_seconds=round(max_dur, 1),
        p95_duration_seconds=round(p95, 1),
        last_run_time=last_run_time,
    )
