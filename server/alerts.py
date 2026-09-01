"""
Background email alert engine.

- Polls all workspaces for anomalies every ALERT_POLL_INTERVAL seconds (default 300)
- Sends email for new anomalies at or above ALERT_MIN_SEVERITY (default: medium)
- Deduplicates: only alerts once per (job_id, workspace_id, anomaly_type) until it clears
- Uses SMTP (smtplib) -- works with Gmail, Outlook, corporate SMTP

Config env vars:
  ALERT_EMAIL_TO       -- comma-separated recipient addresses (required to enable alerts)
  ALERT_EMAIL_FROM     -- sender address (default: same as SMTP_USER)
  SMTP_HOST            -- SMTP server host (default: smtp.gmail.com)
  SMTP_PORT            -- SMTP port (default: 587)
  SMTP_USER            -- SMTP username
  SMTP_PASSWORD        -- SMTP password or app password
  ALERT_MIN_SEVERITY   -- minimum severity to alert on: low|medium|high|critical (default: medium)
  ALERT_POLL_INTERVAL  -- seconds between checks (default: 300)
"""

import os
import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from server.anomaly import Anomaly, detect_anomalies_for_job
from server.jobs import list_jobs, get_job_runs
from server.workspaces import list_workspaces, get_workspace_client_for

logger = logging.getLogger(__name__)

_COMPANY_NAME = os.environ.get("APP_COMPANY_NAME", "Databricks")
_APP_LABEL = f"{_COMPANY_NAME} Jobs Monitor"

# Severity ordering for comparison
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Active alerts: key = "{workspace_id}:{job_id}:{anomaly_type}" -> first_seen datetime
_active_alerts: dict[str, datetime] = {}


def _get_config() -> dict:
    """Read alert configuration from environment variables."""
    recipients_raw = os.environ.get("ALERT_EMAIL_TO", "").strip()
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()] if recipients_raw else []

    return {
        "enabled": len(recipients) > 0,
        "recipients": recipients,
        "sender": os.environ.get("ALERT_EMAIL_FROM", os.environ.get("SMTP_USER", "noreply@jobs-monitor.local")),
        "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
        "min_severity": os.environ.get("ALERT_MIN_SEVERITY", "medium").lower(),
        "poll_interval": int(os.environ.get("ALERT_POLL_INTERVAL", "300")),
        "app_url": os.environ.get("APP_URL", ""),
    }


def get_alert_status() -> dict:
    """Return alert config status (safe for API -- no passwords)."""
    cfg = _get_config()
    return {
        "enabled": cfg["enabled"],
        "recipients_count": len(cfg["recipients"]),
        "min_severity": cfg["min_severity"],
        "poll_interval_seconds": cfg["poll_interval"],
        "smtp_host": cfg["smtp_host"],
        "active_alert_count": len(_active_alerts),
    }


def get_active_alerts() -> list[dict]:
    """Return currently active (deduplicated) alerts."""
    result = []
    for key, first_seen in _active_alerts.items():
        parts = key.split(":", 2)
        if len(parts) == 3:
            result.append({
                "workspace_id": parts[0],
                "job_id": int(parts[1]) if parts[1].isdigit() else parts[1],
                "anomaly_type": parts[2],
                "first_seen": first_seen.isoformat(),
            })
    return result


def _severity_meets_threshold(severity: str, min_severity: str) -> bool:
    """Check if an anomaly severity meets the minimum threshold."""
    return SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER.get(min_severity, 1)


def _alert_key(workspace_id: str, anomaly: Anomaly) -> str:
    """Generate deduplication key for an anomaly."""
    return f"{workspace_id}:{anomaly.job_id}:{anomaly.anomaly_type}"


SEVERITY_COLORS = {
    "low": "#3b82f6",
    "medium": "#eab308",
    "high": "#f97316",
    "critical": "#ef4444",
}


def _build_alert_email_html(anomaly: Anomaly, workspace_id: str, workspace_name: str, app_url: str) -> str:
    """Build HTML email body for an anomaly alert."""
    color = SEVERITY_COLORS.get(anomaly.severity, "#6b7280")
    job_link = f"{app_url}/" if app_url else "#"

    current_val = f"{anomaly.current_value}" if anomaly.current_value is not None else "N/A"
    expected_val = f"{anomaly.expected_value}" if anomaly.expected_value is not None else "N/A"

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #111; color: #e5e7eb; padding: 24px; border-radius: 12px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
            <div style="width: 40px; height: 40px; border-radius: 8px; background: linear-gradient(135deg, #E31837, #FF3621); display: flex; align-items: center; justify-content: center; color: white; font-size: 18px;">&#9888;</div>
            <div>
                <div style="font-size: 16px; font-weight: 700; color: white;">{_APP_LABEL} Alert</div>
                <div style="font-size: 12px; color: #9ca3af;">Anomaly Detected</div>
            </div>
        </div>

        <div style="background: #1a1a1a; border: 1px solid #333; border-left: 4px solid {color}; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="background: {color}22; color: {color}; border: 1px solid {color}44; border-radius: 4px; padding: 2px 10px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">{anomaly.severity}</span>
                <span style="font-size: 12px; color: #9ca3af;">{anomaly.anomaly_type}</span>
            </div>

            <div style="font-size: 15px; font-weight: 600; color: white; margin-bottom: 8px;">{anomaly.job_name}</div>
            <div style="font-size: 13px; color: #d1d5db; line-height: 1.6; margin-bottom: 12px;">{anomaly.message}</div>

            <table style="font-size: 12px; color: #9ca3af; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Workspace</td>
                    <td style="padding: 4px 0;">{workspace_name}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Job ID</td>
                    <td style="padding: 4px 0;">{anomaly.job_id}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Current Value</td>
                    <td style="padding: 4px 0;">{current_val}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Expected Value</td>
                    <td style="padding: 4px 0;">{expected_val}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Detected At</td>
                    <td style="padding: 4px 0;">{anomaly.detected_at.strftime('%Y-%m-%d %H:%M UTC')}</td>
                </tr>
            </table>
        </div>

        <a href="{job_link}" style="display: inline-block; background: linear-gradient(135deg, #E31837, #FF3621); color: white; text-decoration: none; border-radius: 6px; padding: 10px 20px; font-size: 13px; font-weight: 600;">View in Dashboard</a>

        <div style="margin-top: 20px; font-size: 11px; color: #6b7280; border-top: 1px solid #333; padding-top: 12px;">
            {_APP_LABEL} &middot; Automated alert
        </div>
    </div>
    """


def _build_resolved_email_html(alert_key: str, workspace_name: str) -> str:
    """Build HTML email body for a resolved alert."""
    parts = alert_key.split(":", 2)
    job_id = parts[1] if len(parts) > 1 else "unknown"
    anomaly_type = parts[2] if len(parts) > 2 else "unknown"

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #111; color: #e5e7eb; padding: 24px; border-radius: 12px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
            <div style="width: 40px; height: 40px; border-radius: 8px; background: linear-gradient(135deg, #16a34a, #22c55e); display: flex; align-items: center; justify-content: center; color: white; font-size: 18px;">&#10003;</div>
            <div>
                <div style="font-size: 16px; font-weight: 700; color: white;">Alert Resolved</div>
                <div style="font-size: 12px; color: #9ca3af;">{_APP_LABEL}</div>
            </div>
        </div>

        <div style="background: #1a1a1a; border: 1px solid #333; border-left: 4px solid #22c55e; border-radius: 8px; padding: 16px;">
            <div style="font-size: 13px; color: #d1d5db; line-height: 1.6;">
                The following anomaly has been resolved and is no longer detected:
            </div>
            <table style="font-size: 12px; color: #9ca3af; border-collapse: collapse; margin-top: 12px;">
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Workspace</td>
                    <td style="padding: 4px 0;">{workspace_name}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Job ID</td>
                    <td style="padding: 4px 0;">{job_id}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 16px 4px 0; font-weight: 600; color: #6b7280;">Anomaly Type</td>
                    <td style="padding: 4px 0;">{anomaly_type}</td>
                </tr>
            </table>
        </div>

        <div style="margin-top: 20px; font-size: 11px; color: #6b7280; border-top: 1px solid #333; padding-top: 12px;">
            {_APP_LABEL} &middot; Automated alert
        </div>
    </div>
    """


def _send_email(subject: str, html_body: str, cfg: dict) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if not cfg["recipients"]:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(cfg["recipients"])
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30) as server:
            server.starttls()
            if cfg["smtp_user"] and cfg["smtp_password"]:
                server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.sendmail(cfg["sender"], cfg["recipients"], msg.as_string())
        logger.info(f"Alert email sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return False


def send_test_email() -> dict:
    """Send a test email to verify configuration. Returns status dict."""
    cfg = _get_config()
    if not cfg["enabled"]:
        return {"success": False, "error": "Alerts not configured. Set ALERT_EMAIL_TO environment variable."}

    subject = f"[TEST] {_APP_LABEL} - Alert System Test"
    html = """
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #111; color: #e5e7eb; padding: 24px; border-radius: 12px;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
            <div style="width: 40px; height: 40px; border-radius: 8px; background: linear-gradient(135deg, #6366f1, #8b5cf6); display: flex; align-items: center; justify-content: center; color: white; font-size: 18px;">&#10003;</div>
            <div>
                <div style="font-size: 16px; font-weight: 700; color: white;">Test Alert - Success</div>
                <div style="font-size: 12px; color: #9ca3af;">{_APP_LABEL}</div>
            </div>
        </div>
        <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 8px; padding: 16px;">
            <div style="font-size: 13px; color: #d1d5db; line-height: 1.6;">
                This is a test email from the {_APP_LABEL} alert system.
                If you received this email, your alert configuration is working correctly.
            </div>
        </div>
        <div style="margin-top: 20px; font-size: 11px; color: #6b7280; border-top: 1px solid #333; padding-top: 12px;">
            {_APP_LABEL} &middot; Test alert
        </div>
    </div>
    """

    success = _send_email(subject, html, cfg)
    if success:
        return {"success": True, "message": f"Test email sent to {len(cfg['recipients'])} recipient(s)."}
    else:
        return {"success": False, "error": "Failed to send test email. Check SMTP configuration and credentials."}


async def _poll_once() -> None:
    """Run one poll cycle: detect anomalies across all workspaces, send new alerts, clear resolved."""
    global _active_alerts

    cfg = _get_config()
    if not cfg["enabled"]:
        return

    min_severity = cfg["min_severity"]
    current_keys: set[str] = set()

    try:
        workspaces = list_workspaces()
    except Exception as e:
        logger.error(f"Alert poll: failed to list workspaces: {e}")
        return

    for ws in workspaces:
        try:
            w = get_workspace_client_for(ws.workspace_id)
            jobs = list_jobs(w)

            for job_info in jobs:
                try:
                    runs = get_job_runs(w, job_info.job_id, limit=20)
                    anomalies = detect_anomalies_for_job(job_info, runs)

                    for anomaly in anomalies:
                        if not _severity_meets_threshold(anomaly.severity, min_severity):
                            continue

                        key = _alert_key(ws.workspace_id, anomaly)
                        current_keys.add(key)

                        if key not in _active_alerts:
                            # New anomaly -- send alert
                            _active_alerts[key] = datetime.now(timezone.utc)
                            subject = f"[{anomaly.severity.upper()}] {anomaly.job_name} - {anomaly.anomaly_type} | {_APP_LABEL}"
                            html = _build_alert_email_html(anomaly, ws.workspace_id, ws.workspace_name, cfg["app_url"])
                            _send_email(subject, html, cfg)

                except Exception as e:
                    logger.warning(f"Alert poll: error processing job {job_info.job_id} in {ws.workspace_id}: {e}")

        except Exception as e:
            logger.warning(f"Alert poll: error processing workspace {ws.workspace_id}: {e}")

    # Check for resolved alerts
    resolved_keys = set(_active_alerts.keys()) - current_keys
    for key in resolved_keys:
        # Find workspace name for the resolved alert
        ws_id = key.split(":")[0]
        ws_name = ws_id
        for ws in workspaces:
            if ws.workspace_id == ws_id:
                ws_name = ws.workspace_name
                break

        subject = f"[RESOLVED] {key.split(':')[2]} for job {key.split(':')[1]} | {_APP_LABEL}"
        html = _build_resolved_email_html(key, ws_name)
        _send_email(subject, html, cfg)
        del _active_alerts[key]

    logger.info(f"Alert poll complete: {len(current_keys)} active anomalies, {len(resolved_keys)} resolved")


async def start_alert_loop() -> None:
    """Background loop that polls for anomalies and sends email alerts."""
    cfg = _get_config()
    interval = cfg["poll_interval"]
    logger.info(f"Alert loop started: polling every {interval}s, min severity={cfg['min_severity']}")

    while True:
        try:
            await _poll_once()
        except asyncio.CancelledError:
            logger.info("Alert loop cancelled")
            break
        except Exception as e:
            logger.error(f"Alert poll cycle failed: {e}")

        await asyncio.sleep(interval)
