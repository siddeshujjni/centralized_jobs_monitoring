"""Setup diagnostics route — helps customers identify why jobs aren't appearing."""

import os
import logging
from fastapi import APIRouter
from server.config import get_workspace_client, IS_DATABRICKS_APP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["setup"])

_PLACEHOLDER_URL = "your-workspace.cloud.databricks.com"


@router.get("/setup/check")
def get_setup_check():
    """Diagnose common configuration problems that cause 0 jobs to appear.

    Returns a structured list of issues and warnings with actionable fix instructions.
    This endpoint is safe to call without auth context — it only reads env vars and
    makes read-only SDK calls.
    """
    issues = []
    warnings = []
    info = []
    job_count = 0
    sp_identity = None

    # ── 1. WORKSPACE_URLS check ───────────────────────────────────────────────
    workspace_urls_raw = os.environ.get("WORKSPACE_URLS", "")
    urls = [u.strip().rstrip("/") for u in workspace_urls_raw.split(",") if u.strip()]

    placeholder_urls = [u for u in urls if _PLACEHOLDER_URL in u]
    real_urls = [u for u in urls if _PLACEHOLDER_URL not in u]

    if not urls or all(_PLACEHOLDER_URL in u for u in urls):
        issues.append({
            "type": "missing_workspace_url",
            "title": "WORKSPACE_URLS not configured",
            "detail": (
                "WORKSPACE_URLS is still set to the template placeholder. "
                "The app does not know which Databricks workspace to connect to."
            ),
            "fix": (
                "In the Databricks App Settings UI, set:\n"
                "  WORKSPACE_URLS = https://<your-workspace>.cloud.databricks.com\n\n"
                "The slug for the token variable is the hostname prefix, uppercased with dashes "
                "replaced by underscores. For example:\n"
                "  https://my-prod.cloud.databricks.com  →  WORKSPACE_TOKEN_MY_PROD"
            ),
        })
        return _response(issues, warnings, info, job_count, sp_identity)

    # Warn about placeholder URLs mixed with real ones
    if placeholder_urls:
        warnings.append({
            "type": "placeholder_url_present",
            "title": "Template placeholder URL still present",
            "detail": f"WORKSPACE_URLS contains the placeholder '{_PLACEHOLDER_URL}'. Remove it.",
            "fix": "Edit WORKSPACE_URLS in App Settings and remove the placeholder entry.",
        })

    # ── 2. Token check per workspace ─────────────────────────────────────────
    missing_tokens = []
    for url in real_urls:
        slug = url.replace("https://", "").split(".")[0].upper().replace("-", "_")
        token = os.environ.get(f"WORKSPACE_TOKEN_{slug}")
        if not token:
            missing_tokens.append((slug, url))

    if missing_tokens:
        for slug, url in missing_tokens:
            issues.append({
                "type": "missing_token",
                "title": f"No PAT token for workspace {slug}",
                "detail": (
                    f"WORKSPACE_TOKEN_{slug} is not set. Without it the app uses the "
                    "auto-injected service principal, which is NOT a workspace admin and "
                    "cannot list jobs created by other users."
                ),
                "fix": (
                    f"1. In Databricks ({url}) go to Settings → Developer → Access tokens → Generate new token.\n"
                    f"2. In the App Settings UI add:\n"
                    f"   WORKSPACE_TOKEN_{slug} = <your-token>\n\n"
                    "The token owner must have 'Can View' on all jobs or be a workspace admin."
                ),
            })

    # ── 3. Connectivity + job visibility test ────────────────────────────────
    try:
        w = get_workspace_client()

        # Identify who the app is authenticating as
        try:
            me = w.current_user.me()
            sp_identity = me.user_name or me.display_name
        except Exception:
            pass

        from server.jobs import list_jobs
        jobs = list_jobs(w)
        job_count = len(jobs)

        if job_count == 0 and not issues:
            warnings.append({
                "type": "zero_jobs_visible",
                "title": "Connected but 0 jobs visible",
                "detail": (
                    f"The app authenticated successfully{f' as {sp_identity}' if sp_identity else ''} "
                    "but found no jobs. The account may not have permission to see other users' jobs."
                ),
                "fix": (
                    "Set WORKSPACE_TOKEN_<SLUG> with a PAT from an account that has "
                    "'Can View' on all jobs or workspace-admin rights.\n\n"
                    "To find the correct slug: take the workspace hostname prefix, uppercase it, "
                    "replace dashes with underscores.\n"
                    "Example: my-workspace.cloud.databricks.com → WORKSPACE_TOKEN_MY_WORKSPACE"
                ),
            })
        elif job_count > 0:
            info.append({
                "type": "connection_ok",
                "title": "Connected successfully",
                "detail": f"Authenticated{f' as {sp_identity}' if sp_identity else ''}, {job_count} job(s) visible.",
            })

    except Exception as e:
        err_str = str(e)
        if "cannot get access token" in err_str or "default auth" in err_str:
            issues.append({
                "type": "auth_error",
                "title": "Authentication failed",
                "detail": (
                    "The app could not obtain credentials to connect to your Databricks workspace. "
                    "This usually means no PAT token is configured and the service principal "
                    "credentials are not available."
                ),
                "fix": (
                    "Set WORKSPACE_TOKEN_<SLUG> in App Settings with a valid PAT token.\n"
                    "The slug is the workspace hostname prefix, uppercased, dashes→underscores."
                ),
            })
        else:
            issues.append({
                "type": "connection_error",
                "title": "Cannot connect to workspace",
                "detail": err_str[:300],
                "fix": "Verify WORKSPACE_URLS is correct and the PAT token has not expired.",
            })

    return _response(issues, warnings, info, job_count, sp_identity)


def _response(issues, warnings, info, job_count, sp_identity):
    if issues:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "job_count": job_count,
        "sp_identity": sp_identity,
        "issues": issues,
        "warnings": warnings,
        "info": info,
    }
