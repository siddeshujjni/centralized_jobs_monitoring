"""Configuration module - handles auth for both local dev and Databricks Apps."""

import os
import threading
from databricks.sdk import WorkspaceClient

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable ("true"/"1"/"yes"/"on" = True)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# AI-powered analysis (Claude via Databricks Foundation Models) is OPTIONAL and
# disabled by default. Set ENABLE_AI_ANALYSIS=true to turn it on. When off, the
# AI endpoints are unavailable and the AI panels are hidden in the UI — the app
# still provides full statistical anomaly detection without any LLM calls.
AI_ANALYSIS_ENABLED = _env_flag("ENABLE_AI_ANALYSIS", default=False)

_CONFLICT_KEYS = [
    "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_TOKEN", "DATABRICKS_AZURE_CLIENT_ID",
    "DATABRICKS_AZURE_CLIENT_SECRET",
]

# Lock that serialises the brief window where _CONFLICT_KEYS are absent from
# os.environ.  Without this, a concurrent call to WorkspaceClient() (e.g. from
# the Lakebase poller running in a ThreadPoolExecutor) can see the vars missing
# and fall all the way through to "databricks cli cannot get access to token".
_env_lock = threading.Lock()


def _suppress_m2m_and_create(host: str, token: str) -> WorkspaceClient:
    """Create a PAT-based WorkspaceClient, temporarily suppressing injected
    M2M credentials to avoid 'more than one authorization method' errors.

    Thread-safe: holds _env_lock for the brief pop/restore window so that
    concurrent WorkspaceClient() calls never see an empty auth environment.
    """
    with _env_lock:
        saved = {k: os.environ.pop(k, None) for k in _CONFLICT_KEYS}
        try:
            return WorkspaceClient(host=host, token=token)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


def _home_workspace_slug() -> str:
    """Derive the slug for the deployment workspace from DATABRICKS_HOST."""
    host = os.environ.get("DATABRICKS_HOST", "")
    return host.replace("https://", "").split(".")[0].upper().replace("-", "_")


def get_workspace_client() -> WorkspaceClient:
    """Get WorkspaceClient for the default workspace.

    Auth priority (Databricks Apps):
    1. WORKSPACE_TOKEN_<HOME_SLUG>  — explicit admin PAT for the deployment workspace
    2. First workspace in WORKSPACE_URLS that has a WORKSPACE_TOKEN_<SLUG> set
       (fallback when SP lacks job visibility on the deployment workspace)
    3. Auto-injected service principal credentials

    Local dev:
    - Uses DATABRICKS_PROFILE (default: DEFAULT)
    """
    if IS_DATABRICKS_APP:
        # 1. Explicit token for the home/deployment workspace
        slug = _home_workspace_slug()
        token = os.environ.get(f"WORKSPACE_TOKEN_{slug}")
        if token:
            host = os.environ.get("DATABRICKS_HOST", "")
            if host and not host.startswith("http"):
                host = f"https://{host}"
            return _suppress_m2m_and_create(host, token)

        # 2. Fall back to first workspace in WORKSPACE_URLS that has a PAT token.
        #    This handles the common case where the app service principal does not
        #    have workspace-admin rights and therefore cannot list all jobs.
        workspace_urls_env = os.environ.get("WORKSPACE_URLS", "")
        for url in (u.strip().rstrip("/") for u in workspace_urls_env.split(",") if u.strip()):
            ws_slug = url.replace("https://", "").split(".")[0].upper().replace("-", "_")
            ws_token = os.environ.get(f"WORKSPACE_TOKEN_{ws_slug}")
            if ws_token:
                return _suppress_m2m_and_create(url, ws_token)

        # 3. Service principal (may have limited job visibility)
        return WorkspaceClient()

    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_sp_workspace_client() -> WorkspaceClient:
    """Get a WorkspaceClient using ONLY service principal / OAuth credentials.

    This is used for Lakebase authentication — the SP has CAN_CONNECT permission
    on the database and Lakebase requires an OAuth token (not a PAT).
    Unlike get_workspace_client(), this never returns a PAT-based client.
    """
    if IS_DATABRICKS_APP:
        # Use auto-injected SP credentials (DATABRICKS_CLIENT_ID/SECRET)
        return WorkspaceClient()
    # Local dev: use configured profile (U2M or PAT — asyncpg works with both)
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_oauth_token() -> str:
    """Get OAuth bearer token for API calls (works with M2M and U2M auth)."""
    w = get_workspace_client()
    try:
        auth_headers = w.config.authenticate()
        if auth_headers and "Authorization" in auth_headers:
            return auth_headers["Authorization"].replace("Bearer ", "")
    except Exception:
        pass
    return os.environ.get("DATABRICKS_TOKEN", "")


def get_workspace_host() -> str:
    """Get workspace host URL with https:// scheme."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    w = get_workspace_client()
    return w.config.host
