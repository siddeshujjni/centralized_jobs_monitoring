"""AI-powered analysis using Databricks Foundation Model API (Claude).

Provides intelligent job health analysis, root-cause explanations, and
actionable recommendations on top of the statistical anomaly detectors.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from server.jobs import JobInfo, JobRun, JobStats
from server.anomaly import Anomaly
from server.llm import chat
from server.db import is_configured as lakebase_configured, get_cached_insight, store_insight

logger = logging.getLogger(__name__)

_COMPANY_NAME = os.environ.get("APP_COMPANY_NAME", "the organization")

SYSTEM_PROMPT = f"""You are an expert Databricks platform engineer and SRE analyst for {_COMPANY_NAME}.
Your job is to analyse Databricks job monitoring data and provide concise, actionable insights.

Always respond with valid JSON matching the exact schema requested.
Be specific, factual, and brief. Avoid generic advice — tailor analysis to the data provided."""


class RemediationStep(BaseModel):
    priority: int           # 1 = highest priority
    action: str             # Short action title e.g. "Scale up cluster"
    detail: str             # Full explanation of what to do and why
    estimated_impact: str   # "High" | "Medium" | "Low"
    automated: bool         # Can this be automated? (future feature flag)


class JobAIInsight(BaseModel):
    job_id: int
    job_name: str
    health_score: int          # 0-100, where 100 = perfectly healthy
    risk_level: str            # "low" | "medium" | "high" | "critical"
    summary: str               # 1-2 sentence plain-English summary
    root_cause: Optional[str]  # Root cause analysis if anomalies present
    recommendations: list[str] # 2-4 specific, actionable recommendations
    remediation_steps: list[RemediationStep]  # Ordered by priority
    predicted_next_issue: Optional[str]  # Predictive insight if trend is worsening
    generated_at: datetime


class WorkspaceAIInsight(BaseModel):
    overall_health_score: int  # 0-100
    critical_jobs: list[str]   # Job names needing immediate attention
    summary: str               # 2-3 sentence workspace-level summary
    top_risks: list[str]       # Top 3 risks across the workspace
    recommendations: list[str] # Top 3 workspace-level recommendations
    generated_at: datetime


def _anomaly_fingerprint(job_id: int, anomalies: list[Anomaly]) -> str:
    """Build a stable fingerprint from the set of anomaly types and severities for a job.

    Two invocations with the same anomaly types + severities produce the same hash,
    so the LLM result can be reused.
    """
    parts = sorted(f"{a.anomaly_type}:{a.severity}" for a in anomalies)
    raw = f"{job_id}|{'|'.join(parts)}" if parts else f"{job_id}|healthy"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _format_runs_for_prompt(runs: list[JobRun]) -> str:
    """Format run history into a compact string for the prompt."""
    if not runs:
        return "No runs available."
    lines = []
    for r in runs[:10]:  # Limit to last 10 to keep token count manageable
        start = r.start_time.strftime("%Y-%m-%d %H:%M") if r.start_time else "unknown"
        dur = f"{r.duration_seconds:.0f}s" if r.duration_seconds else "?"
        status = r.result_state or r.state
        lines.append(f"  - {start}: {status} in {dur}")
    return "\n".join(lines)


def _format_anomalies_for_prompt(anomalies: list[Anomaly]) -> str:
    if not anomalies:
        return "No anomalies detected."
    return "\n".join(
        f"  - [{a.severity.upper()}] {a.anomaly_type}: {a.message}"
        for a in anomalies
    )


async def analyze_job(
    job_info: JobInfo,
    runs: list[JobRun],
    stats: JobStats,
    anomalies: list[Anomaly],
    workspace_id: str = "",
) -> JobAIInsight:
    """Use Claude to produce an AI-powered health analysis for a single job.

    Checks Lakebase cache first — if the same anomaly pattern was already analysed
    for this job, returns the cached insight instead of making an LLM call.
    """
    fingerprint = _anomaly_fingerprint(job_info.job_id, anomalies)
    cache_key = f"job:{workspace_id or 'default'}:{job_info.job_id}:{fingerprint}"

    # ── Check cache ──
    if lakebase_configured():
        cached = await get_cached_insight(cache_key)
        if cached:
            logger.info(f"Cache HIT for job {job_info.job_id} (key={cache_key[:24]}…)")
            try:
                return JobAIInsight(
                    job_id=job_info.job_id,
                    job_name=job_info.name,
                    health_score=int(cached.get("health_score", 50)),
                    risk_level=cached.get("risk_level", "medium"),
                    summary=cached.get("summary", ""),
                    root_cause=cached.get("root_cause"),
                    recommendations=cached.get("recommendations", []),
                    remediation_steps=[
                        RemediationStep(**s) for s in cached.get("remediation_steps", [])
                    ],
                    predicted_next_issue=cached.get("predicted_next_issue"),
                    generated_at=datetime.fromisoformat(cached["generated_at"])
                        if cached.get("generated_at") else datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.warning(f"Cache parse failed, will call LLM: {e}")

    logger.info(f"Cache MISS for job {job_info.job_id} — calling LLM")

    runs_text = _format_runs_for_prompt(runs)
    anomalies_text = _format_anomalies_for_prompt(anomalies)

    user_message = f"""Analyse this Databricks job and respond with JSON only.

JOB: {job_info.name} (ID: {job_info.job_id})
SCHEDULE: {job_info.schedule or 'No schedule (manual/trigger)'}
CURRENT STATUS: {job_info.status}
CREATOR: {job_info.creator or 'unknown'}

STATISTICS (last 20 runs):
- Total runs: {stats.total_runs}
- Success rate: {stats.success_rate}%
- Avg duration: {stats.avg_duration_seconds:.1f}s
- Min duration: {stats.min_duration_seconds:.1f}s
- Max duration: {stats.max_duration_seconds:.1f}s
- P95 duration: {stats.p95_duration_seconds:.1f}s
- Last run: {stats.last_run_time.strftime('%Y-%m-%d %H:%M UTC') if stats.last_run_time else 'never'}

DETECTED ANOMALIES:
{anomalies_text}

RECENT RUN HISTORY:
{runs_text}

Respond with this exact JSON structure (no markdown, no extra text):
{{
  "health_score": <integer 0-100>,
  "risk_level": "<low|medium|high|critical>",
  "summary": "<1-2 sentence plain English summary of job health>",
  "root_cause": "<specific root cause if anomalies present, null if healthy>",
  "recommendations": ["<recommendation 1>", "<recommendation 2>", "<recommendation 3>"],
  "remediation_steps": [
    {{
      "priority": 1,
      "action": "<short action title>",
      "detail": "<what to do, why, specific commands or settings if applicable>",
      "estimated_impact": "<High|Medium|Low>",
      "automated": <true|false>
    }}
  ],
  "predicted_next_issue": "<predictive insight if trend is worsening, null if stable>"
}}

For remediation_steps, provide 2-4 steps ordered by priority. Steps should be specific and actionable, not generic advice. Examples:
- Increase max_retries from 1 to 3 in job settings
- Add a data quality check task before the main transformation task
- Switch from on-demand to spot instances to reduce cost, set fallback to on-demand
- Set a job timeout of 2x average duration to auto-terminate runaway runs"""

    response_text = await chat(SYSTEM_PROMPT, user_message)

    # Parse JSON response
    try:
        # Strip any accidental markdown fences
        clean = response_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)

        # Parse remediation steps
        raw_steps = data.get("remediation_steps", [])
        remediation_steps = []
        for step in raw_steps:
            try:
                remediation_steps.append(RemediationStep(
                    priority=int(step.get("priority", len(remediation_steps) + 1)),
                    action=step.get("action", "Review job configuration"),
                    detail=step.get("detail", ""),
                    estimated_impact=step.get("estimated_impact", "Medium"),
                    automated=bool(step.get("automated", False)),
                ))
            except Exception:
                pass

        insight = JobAIInsight(
            job_id=job_info.job_id,
            job_name=job_info.name,
            health_score=int(data.get("health_score", 50)),
            risk_level=data.get("risk_level", "medium"),
            summary=data.get("summary", "Analysis unavailable."),
            root_cause=data.get("root_cause"),
            recommendations=data.get("recommendations", []),
            remediation_steps=remediation_steps,
            predicted_next_issue=data.get("predicted_next_issue"),
            generated_at=datetime.now(timezone.utc),
        )

        # ── Store in cache ──
        if lakebase_configured():
            try:
                await store_insight(
                    cache_key=cache_key,
                    job_id=job_info.job_id,
                    workspace_id=workspace_id or "default",
                    anomaly_fingerprint=fingerprint,
                    insight=insight.model_dump(mode="json"),
                )
                logger.info(f"Cached AI insight for job {job_info.job_id}")
            except Exception as e:
                logger.warning(f"Failed to cache insight: {e}")

        return insight
    except Exception as e:
        logger.error(f"Failed to parse AI response for job {job_info.job_id}: {e}\nResponse: {response_text}")
        # Return a safe fallback rather than crashing
        return JobAIInsight(
            job_id=job_info.job_id,
            job_name=job_info.name,
            health_score=50,
            risk_level="medium",
            summary="AI analysis encountered an error parsing the response.",
            root_cause=None,
            recommendations=["Check the job logs directly in the Databricks UI."],
            remediation_steps=[],
            predicted_next_issue=None,
            generated_at=datetime.now(timezone.utc),
        )


async def analyze_workspace(
    jobs: list[JobInfo],
    all_anomalies: list[Anomaly],
) -> WorkspaceAIInsight:
    """Use Claude to produce a workspace-level health summary."""

    # Build a compact job health table
    job_lines = []
    for j in jobs:
        anomaly_count = sum(1 for a in all_anomalies if a.job_id == j.job_id)
        job_lines.append(f"  - {j.name}: status={j.status}, anomalies={anomaly_count}")
    jobs_text = "\n".join(job_lines) if job_lines else "No jobs found."

    critical_anomalies = [a for a in all_anomalies if a.severity in ("critical", "high")]
    anomaly_lines = _format_anomalies_for_prompt(critical_anomalies[:10])

    user_message = f"""Analyse the overall health of this Databricks workspace for {_COMPANY_NAME} and respond with JSON only.

WORKSPACE JOB SUMMARY ({len(jobs)} jobs total):
{jobs_text}

CRITICAL/HIGH ANOMALIES:
{anomaly_lines}

COUNTS:
- Total anomalies: {len(all_anomalies)}
- Critical: {sum(1 for a in all_anomalies if a.severity == 'critical')}
- High: {sum(1 for a in all_anomalies if a.severity == 'high')}
- Medium: {sum(1 for a in all_anomalies if a.severity == 'medium')}
- Low: {sum(1 for a in all_anomalies if a.severity == 'low')}

Respond with this exact JSON structure (no markdown, no extra text):
{{
  "overall_health_score": <integer 0-100>,
  "critical_jobs": ["<job name 1>", "<job name 2>"],
  "summary": "<2-3 sentence workspace health summary for the ops team>",
  "top_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "recommendations": ["<recommendation 1>", "<recommendation 2>", "<recommendation 3>"]
}}"""

    response_text = await chat(SYSTEM_PROMPT, user_message)

    try:
        clean = response_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        return WorkspaceAIInsight(
            overall_health_score=int(data.get("overall_health_score", 75)),
            critical_jobs=data.get("critical_jobs", []),
            summary=data.get("summary", "Analysis unavailable."),
            top_risks=data.get("top_risks", []),
            recommendations=data.get("recommendations", []),
            generated_at=datetime.now(timezone.utc),
        )
    except Exception as e:
        logger.error(f"Failed to parse workspace AI response: {e}\nResponse: {response_text}")
        return WorkspaceAIInsight(
            overall_health_score=75,
            critical_jobs=[],
            summary="AI workspace analysis encountered an error.",
            top_risks=["Review anomaly dashboard for current issues."],
            recommendations=["Re-run the workspace analysis."],
            generated_at=datetime.now(timezone.utc),
        )
