"""Anomaly detection engine for Databricks Jobs monitoring."""

import math
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel
from server.jobs import JobRun, JobInfo

logger = logging.getLogger(__name__)


class AnomalyType(str, Enum):
    DURATION_SPIKE = "duration_spike"
    FAILURE_RATE = "failure_rate"
    LONG_RUNNING = "long_running"
    MISSED_SCHEDULE = "missed_schedule"
    CONSECUTIVE_FAILURES = "consecutive_failures"


class Anomaly(BaseModel):
    job_id: int
    job_name: str
    anomaly_type: AnomalyType
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    detected_at: datetime
    current_value: Optional[float] = None
    expected_value: Optional[float] = None


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def detect_duration_spike(job_name: str, job_id: int, runs: list[JobRun]) -> Optional[Anomaly]:
    """Detect if the latest run duration is >2 stddev above the mean of last 10 runs."""
    completed = [r for r in runs if r.result_state == "SUCCESS" and r.duration_seconds and r.duration_seconds > 0]
    if len(completed) < 3:
        return None

    latest = completed[0]
    historical = completed[1:11]  # last 10 excluding current

    durations = [r.duration_seconds for r in historical]
    if not durations:
        return None

    m = _mean(durations)
    sd = _stddev(durations)

    if sd == 0:
        return None

    threshold = m + 2 * sd
    if latest.duration_seconds > threshold:
        ratio = latest.duration_seconds / m if m > 0 else 0
        severity = "low"
        if ratio > 3:
            severity = "critical"
        elif ratio > 2.5:
            severity = "high"
        elif ratio > 2:
            severity = "medium"

        return Anomaly(
            job_id=job_id,
            job_name=job_name,
            anomaly_type=AnomalyType.DURATION_SPIKE,
            severity=severity,
            message=f"Latest run took {latest.duration_seconds:.0f}s, which is {ratio:.1f}x the average of {m:.0f}s",
            detected_at=datetime.now(timezone.utc),
            current_value=round(latest.duration_seconds, 1),
            expected_value=round(m, 1),
        )
    return None


def detect_failure_rate(job_name: str, job_id: int, runs: list[JobRun]) -> Optional[Anomaly]:
    """Detect if >3 failures in last 5 runs."""
    completed = [r for r in runs if r.result_state in ("SUCCESS", "FAILED", "TIMEDOUT")]
    last_5 = completed[:5]

    if len(last_5) < 5:
        return None

    failures = sum(1 for r in last_5 if r.result_state in ("FAILED", "TIMEDOUT"))

    if failures >= 3:
        severity = "critical" if failures >= 5 else "high" if failures >= 4 else "medium"
        return Anomaly(
            job_id=job_id,
            job_name=job_name,
            anomaly_type=AnomalyType.FAILURE_RATE,
            severity=severity,
            message=f"{failures} out of last 5 runs failed",
            detected_at=datetime.now(timezone.utc),
            current_value=float(failures),
            expected_value=0.0,
        )
    return None


def detect_long_running(job_name: str, job_id: int, runs: list[JobRun]) -> Optional[Anomaly]:
    """Detect if a currently running job exceeds 2x its average duration."""
    running = [r for r in runs if r.state == "RUNNING"]
    if not running:
        return None

    current_run = running[0]
    if not current_run.start_time:
        return None

    elapsed = (datetime.now(timezone.utc) - current_run.start_time).total_seconds()

    completed = [r for r in runs if r.result_state == "SUCCESS" and r.duration_seconds and r.duration_seconds > 0]
    if len(completed) < 3:
        return None

    avg_dur = _mean([r.duration_seconds for r in completed[:10]])
    if avg_dur <= 0:
        return None

    if elapsed > 2 * avg_dur:
        ratio = elapsed / avg_dur
        severity = "critical" if ratio > 5 else "high" if ratio > 3 else "medium"
        return Anomaly(
            job_id=job_id,
            job_name=job_name,
            anomaly_type=AnomalyType.LONG_RUNNING,
            severity=severity,
            message=f"Job running for {elapsed:.0f}s, which is {ratio:.1f}x the average of {avg_dur:.0f}s",
            detected_at=datetime.now(timezone.utc),
            current_value=round(elapsed, 1),
            expected_value=round(avg_dur, 1),
        )
    return None


def detect_missed_schedule(job_name: str, job_id: int, runs: list[JobRun], schedule: Optional[str] = None) -> Optional[Anomaly]:
    """Detect if a scheduled job hasn't run in >2x its typical interval."""
    if not schedule:
        return None

    if len(runs) < 2:
        return None

    # Calculate typical interval from last few runs
    start_times = [r.start_time for r in runs if r.start_time][:10]
    if len(start_times) < 2:
        return None

    intervals = []
    for i in range(len(start_times) - 1):
        diff = (start_times[i] - start_times[i + 1]).total_seconds()
        if diff > 0:
            intervals.append(diff)

    if not intervals:
        return None

    avg_interval = _mean(intervals)
    if avg_interval <= 0:
        return None

    time_since_last = (datetime.now(timezone.utc) - start_times[0]).total_seconds()

    if time_since_last > 2 * avg_interval:
        ratio = time_since_last / avg_interval
        severity = "high" if ratio > 5 else "medium" if ratio > 3 else "low"
        hours_since = time_since_last / 3600
        return Anomaly(
            job_id=job_id,
            job_name=job_name,
            anomaly_type=AnomalyType.MISSED_SCHEDULE,
            severity=severity,
            message=f"Scheduled job hasn't run in {hours_since:.1f}h, typical interval is {avg_interval/3600:.1f}h",
            detected_at=datetime.now(timezone.utc),
            current_value=round(time_since_last, 1),
            expected_value=round(avg_interval, 1),
        )
    return None


def detect_consecutive_failures(job_name: str, job_id: int, runs: list[JobRun]) -> Optional[Anomaly]:
    """Detect 2+ consecutive failures."""
    completed = [r for r in runs if r.result_state in ("SUCCESS", "FAILED", "TIMEDOUT")]
    if len(completed) < 2:
        return None

    consecutive = 0
    for r in completed:
        if r.result_state in ("FAILED", "TIMEDOUT"):
            consecutive += 1
        else:
            break

    if consecutive >= 2:
        severity = "critical" if consecutive >= 5 else "high" if consecutive >= 3 else "medium"
        return Anomaly(
            job_id=job_id,
            job_name=job_name,
            anomaly_type=AnomalyType.CONSECUTIVE_FAILURES,
            severity=severity,
            message=f"{consecutive} consecutive failures detected",
            detected_at=datetime.now(timezone.utc),
            current_value=float(consecutive),
            expected_value=0.0,
        )
    return None


def detect_anomalies_for_job(job_info: JobInfo, runs: list[JobRun]) -> list[Anomaly]:
    """Run all anomaly detectors for a single job."""
    anomalies = []

    detectors = [
        lambda: detect_duration_spike(job_info.name, job_info.job_id, runs),
        lambda: detect_failure_rate(job_info.name, job_info.job_id, runs),
        lambda: detect_long_running(job_info.name, job_info.job_id, runs),
        lambda: detect_missed_schedule(job_info.name, job_info.job_id, runs, job_info.schedule),
        lambda: detect_consecutive_failures(job_info.name, job_info.job_id, runs),
    ]

    for detector in detectors:
        try:
            result = detector()
            if result:
                anomalies.append(result)
        except Exception as e:
            logger.warning(f"Anomaly detector error for job {job_info.job_id}: {e}")

    return anomalies
