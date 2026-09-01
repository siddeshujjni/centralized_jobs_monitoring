"""
Multi-workspace manager.

Discovery strategy (in order):
1. Databricks AccountClient (if DATABRICKS_ACCOUNT_ID env var is set or account profile configured)
2. WORKSPACE_URLS env var -- comma-separated list of workspace host URLs
3. Fallback: single workspace from existing DEFAULT profile

Each workspace is identified by its URL. We create a WorkspaceClient per workspace,
reusing cached clients.
"""

import os
import configparser
import logging
from pathlib import Path
from databricks.sdk import AccountClient, WorkspaceClient
from databricks.sdk.config import Config
from pydantic import BaseModel

from server.config import IS_DATABRICKS_APP, _suppress_m2m_and_create

logger = logging.getLogger(__name__)

# Internal map: workspace_id -> CLI profile name (not exposed in API)
_workspace_profile_map: dict[str, str] = {}


class WorkspaceInfo(BaseModel):
    workspace_id: str
    workspace_name: str
    workspace_url: str
    environment: str  # "production" | "staging" | "development" | "unknown"
    cloud: str  # "aws" | "azure" | "gcp" | "unknown"


def _infer_environment(name: str) -> str:
    """Infer environment from workspace name."""
    name_lower = name.lower()
    if any(k in name_lower for k in ["prod", "production", "prd"]):
        return "production"
    elif any(k in name_lower for k in ["stag", "staging", "stage", "uat"]):
        return "staging"
    elif any(k in name_lower for k in ["dev", "develop", "sandbox", "test", "qa"]):
        return "development"
    return "unknown"


def _infer_cloud(url: str) -> str:
    if "azuredatabricks" in url:
        return "azure"
    elif "gcp.databricks" in url:
        return "gcp"
    return "aws"


def _read_profiles_from_cfg() -> dict[str, str]:
    """Read ~/.databrickscfg and return a mapping of profile_name -> host."""
    cfg_path = Path.home() / ".databrickscfg"
    if not cfg_path.exists():
        return {}
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path)
    result = {}
    for section in cfg.sections():
        host = cfg.get(section, "host", fallback="").strip()
        if host:
            result[section] = host
    # Also handle [DEFAULT] section (configparser treats it specially)
    default_host = cfg.defaults().get("host", "").strip()
    if default_host:
        result["DEFAULT"] = default_host
    return result


def list_workspaces() -> list[WorkspaceInfo]:
    """Discover all workspaces. Tries strategies in order until one returns results."""
    global _workspace_profile_map
    _workspace_profile_map = {}

    # Strategy 1: AccountClient (set DATABRICKS_ACCOUNT_ID to activate)
    account_id = os.environ.get("DATABRICKS_ACCOUNT_ID")
    if account_id:
        try:
            profile = os.environ.get("DATABRICKS_ACCOUNT_PROFILE", "DEFAULT")
            a = AccountClient(profile=profile)
            workspaces = list(a.workspaces.list())
            if workspaces:
                results = []
                for ws in workspaces:
                    url = f"https://{ws.deployment_name}.cloud.databricks.com"
                    ws_id = str(ws.workspace_id)
                    results.append(WorkspaceInfo(
                        workspace_id=ws_id,
                        workspace_name=ws.workspace_name or f"Workspace {ws_id}",
                        workspace_url=url,
                        environment=_infer_environment(ws.workspace_name or ""),
                        cloud=_infer_cloud(url),
                    ))
                    _workspace_profile_map[ws_id] = profile
                return results
        except Exception as e:
            logger.warning(f"AccountClient discovery failed: {e}")

    # Strategy 2: DATABRICKS_PROFILES env var — comma-separated CLI profile names
    # e.g. DATABRICKS_PROFILES=DEFAULT,e2-demo-field-eng,logfood
    profiles_env = os.environ.get("DATABRICKS_PROFILES", "")
    if profiles_env:
        profile_names = [p.strip() for p in profiles_env.split(",") if p.strip()]
        profile_hosts = _read_profiles_from_cfg()
        results = []
        seen_urls = set()
        for profile_name in profile_names:
            host = profile_hosts.get(profile_name, "")
            if not host or host in seen_urls:
                continue
            seen_urls.add(host)
            slug = host.replace("https://", "").split(".")[0]
            ws_id = f"{slug}"
            name = os.environ.get(f"WORKSPACE_NAME_{profile_name.upper().replace('-', '_')}", slug)
            results.append(WorkspaceInfo(
                workspace_id=ws_id,
                workspace_name=name,
                workspace_url=host,
                environment=_infer_environment(name),
                cloud=_infer_cloud(host),
            ))
            _workspace_profile_map[ws_id] = profile_name
        if results:
            return results

    # Strategy 3: WORKSPACE_URLS env var — works both locally and in Databricks Apps
    # Format: WORKSPACE_URLS=https://ws1.cloud.databricks.com,https://ws2.cloud.databricks.com
    # Optional per-workspace PAT: WORKSPACE_TOKEN_WS1=<token>  (slug = hostname slug, uppercased, dashes→underscores)
    # Optional per-workspace name: WORKSPACE_NAME_WS1=Production
    workspace_urls_env = os.environ.get("WORKSPACE_URLS", "")
    if workspace_urls_env:
        results = []
        seen_urls = set()
        for url in workspace_urls_env.split(","):
            url = url.strip().rstrip("/")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            slug = url.replace("https://", "").split(".")[0]
            env_key = slug.upper().replace("-", "_")
            name = os.environ.get(f"WORKSPACE_NAME_{env_key}", slug)
            results.append(WorkspaceInfo(
                workspace_id=slug,
                workspace_name=name,
                workspace_url=url,
                environment=_infer_environment(name),
                cloud=_infer_cloud(url),
            ))
            # Store profile for local use; token lookup handled in get_workspace_client_for
            _workspace_profile_map[slug] = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
        if results:
            return results

    # Strategy 4: Fallback — single workspace from DEFAULT profile
    try:
        from server.config import get_workspace_client
        w = get_workspace_client()
        host = w.config.host or ""
        slug = host.replace("https://", "").split(".")[0]
        _workspace_profile_map[slug] = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
        return [WorkspaceInfo(
            workspace_id=slug,
            workspace_name=slug,
            workspace_url=host,
            environment=_infer_environment(slug),
            cloud=_infer_cloud(host),
        )]
    except Exception as e:
        logger.error(f"Single workspace fallback failed: {e}")
        return []


# Cache: workspace_id -> WorkspaceClient
_client_cache: dict[str, WorkspaceClient] = {}


def get_workspace_client_for(workspace_id: str) -> WorkspaceClient:
    """Get a WorkspaceClient for a specific workspace.

    Auth priority:
    1. WORKSPACE_TOKEN_<SLUG> env var  — explicit PAT (works in Databricks Apps + locally)
    2. Databricks Apps service principal — auto-injected when IS_DATABRICKS_APP (no token needed if SP has access)
    3. CLI profile mapped during discovery — local dev only
    """
    if workspace_id in _client_cache:
        return _client_cache[workspace_id]

    workspaces = list_workspaces()
    ws = next((w for w in workspaces if w.workspace_id == workspace_id), None)
    if not ws:
        raise ValueError(f"Workspace {workspace_id} not found")

    env_key = workspace_id.upper().replace("-", "_")
    per_workspace_token = os.environ.get(f"WORKSPACE_TOKEN_{env_key}")

    if per_workspace_token:
        # Explicit PAT — use the shared thread-safe helper from config.py so that
        # the brief os.environ pop/restore is serialised with all other callers.
        client = _suppress_m2m_and_create(ws.workspace_url, per_workspace_token)
    elif IS_DATABRICKS_APP:
        # Databricks Apps: use auto-injected service principal credentials
        client = WorkspaceClient(host=ws.workspace_url)
    else:
        # Local: use the CLI profile discovered for this workspace
        profile = _workspace_profile_map.get(workspace_id, os.environ.get("DATABRICKS_PROFILE", "DEFAULT"))
        client = WorkspaceClient(host=ws.workspace_url, profile=profile)

    _client_cache[workspace_id] = client
    return client
