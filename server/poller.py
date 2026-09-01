"""Background poller: syncs Databricks jobs + runs to Lakebase every 60 seconds.

Architecture:
  - Runs as an asyncio background task started from app.py lifespan
  - Each workspace is synced in a ThreadPoolExecutor (Databricks SDK is synchronous)
  - After each sync cycle, job + run data is written to Lakebase via asyncpg
  - OAuth token is refreshed every 45 minutes to avoid Lakebase auth expiry
"""

import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from server.db import (
    init_schema,
    upsert_jobs,
    upsert_runs,
    mark_workspace_synced,
    is_configured,
    refresh_pool,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("LAKEBASE_POLL_INTERVAL", "60"))  # seconds
TOKEN_REFRESH_INTERVAL = 45 * 60  # 45 minutes in seconds

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="poller")


def _sync_workspace_blocking(workspace_id: str):
    """Fetch jobs + runs for one workspace. Runs in a thread (SDK is sync).

    Returns (jobs: list[JobInfo], runs_map: dict, error: str|None).
    """
    try:
        from server.workspaces import get_workspace_client_for
        from server.jobs import list_jobs, bulk_runs_by_job

        client = get_workspace_client_for(workspace_id)
        jobs = list_jobs(client)
        job_ids = {j.job_id for j in jobs}
        runs_map = bulk_runs_by_job(client, job_ids, runs_per_job=10, scan_limit=2000)
        return jobs, runs_map, None
    except Exception as e:
        logger.error(f"Poller: sync error for {workspace_id}: {e}")
        return [], {}, str(e)


async def _poll_once():
    """Execute one full sync cycle across all configured workspaces."""
    from server.workspaces import list_workspaces

    workspaces = list_workspaces()
    if not workspaces:
        logger.warning("Poller: no workspaces found, skipping cycle")
        return

    loop = asyncio.get_event_loop()
    for ws in workspaces:
        try:
            jobs, runs_map, error = await loop.run_in_executor(
                _executor,
                _sync_workspace_blocking,
                ws.workspace_id,
            )
            run_count = 0
            if jobs:
                await upsert_jobs(ws.workspace_id, jobs)
            if runs_map:
                run_count = await upsert_runs(ws.workspace_id, runs_map)
            await mark_workspace_synced(ws.workspace_id, len(jobs), run_count, error)

            if error:
                logger.warning(f"Poller: {ws.workspace_id} completed with error: {error}")
            else:
                total_runs = sum(len(v) for v in runs_map.values())
                logger.info(
                    f"Poller: synced {ws.workspace_id} — "
                    f"{len(jobs)} jobs, {total_runs} runs"
                )
        except Exception as e:
            logger.error(f"Poller: unexpected error for {ws.workspace_id}: {e}")
            await mark_workspace_synced(ws.workspace_id, 0, 0, str(e))


async def start_poller():
    """Long-running background task. Starts immediately, then loops every POLL_INTERVAL seconds.

    Call from app.py lifespan:
        poller_task = asyncio.create_task(start_poller())
    """
    if not is_configured():
        logger.info("Poller: Lakebase not configured (PGHOST not set) — skipping")
        return

    logger.info(f"Poller: starting (interval={POLL_INTERVAL}s)")
    await init_schema()

    # Initial sync on startup
    logger.info("Poller: running initial sync...")
    await _poll_once()
    logger.info("Poller: initial sync complete")

    last_token_refresh = asyncio.get_event_loop().time()

    while True:
        await asyncio.sleep(POLL_INTERVAL)

        # Refresh OAuth token periodically so Lakebase auth doesn't expire
        elapsed = asyncio.get_event_loop().time() - last_token_refresh
        if elapsed >= TOKEN_REFRESH_INTERVAL:
            logger.info("Poller: refreshing Lakebase OAuth token")
            await refresh_pool()
            last_token_refresh = asyncio.get_event_loop().time()

        await _poll_once()
