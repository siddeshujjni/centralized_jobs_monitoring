"""Lakebase (PostgreSQL) connection pool and data access layer.

Lakebase is the Databricks managed PostgreSQL service. It uses OAuth tokens
for authentication, which expire every ~60 minutes — handled via refresh_pool().
"""

import os
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import asyncpg so the app starts even without it installed
try:
    import asyncpg
    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not installed — Lakebase caching disabled")

_pool: Optional["asyncpg.Pool"] = None
_pool_lock = asyncio.Lock()


def is_configured() -> bool:
    """True if Lakebase env vars (PGHOST) are present."""
    return _ASYNCPG_AVAILABLE and bool(os.environ.get("PGHOST"))


def _get_lakebase_token_sync() -> str:
    """Get OAuth token for Lakebase auth (sync). Must be an OAuth token — not a PAT.

    If LAKEBASE_ENDPOINT is set, use Lakebase Autoscaling's
    generate_database_credential (scoped to the endpoint resource name).
    Otherwise fall back to the SP's workspace M2M OAuth token (Lakebase Provisioned).
    """
    from server.config import get_sp_workspace_client
    try:
        w = get_sp_workspace_client()
        endpoint = os.environ.get("LAKEBASE_ENDPOINT")
        if endpoint:
            cred = w.postgres.generate_database_credential(endpoint=endpoint)
            return cred.token or ""
        auth = w.config.authenticate()
        if auth and "Authorization" in auth:
            return auth["Authorization"].replace("Bearer ", "")
    except Exception as e:
        logger.error(f"Failed to obtain Lakebase OAuth token: {e}")
    return ""


async def get_pool() -> Optional["asyncpg.Pool"]:
    """Return the shared asyncpg pool, creating it if needed. Returns None if not configured."""
    global _pool
    if not is_configured():
        return None

    async with _pool_lock:
        if _pool is None or _pool._closed:
            try:
                token = await asyncio.to_thread(_get_lakebase_token_sync)
                _pool = await asyncpg.create_pool(
                    host=os.environ["PGHOST"],
                    port=int(os.environ.get("PGPORT", "5432")),
                    database=os.environ["PGDATABASE"],
                    user=os.environ["PGUSER"],
                    password=token,
                    ssl="require",
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                )
                logger.info("Lakebase connection pool created")
            except Exception as e:
                logger.error(f"Lakebase pool creation failed: {e}")
                _pool = None
    return _pool


async def refresh_pool():
    """Close and recreate pool with a fresh OAuth token. Call every ~45 min."""
    global _pool
    async with _pool_lock:
        if _pool and not _pool._closed:
            try:
                await _pool.close()
            except Exception:
                pass
        _pool = None
    # get_pool() will call _get_lakebase_token_sync() for a fresh token
    await get_pool()
    logger.info("Lakebase pool refreshed with new OAuth token")


async def init_schema():
    """Create tables if they don't exist."""
    pool = await get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id      BIGINT,
                    workspace_id TEXT,
                    name        TEXT,
                    creator     TEXT,
                    created_time TIMESTAMPTZ,
                    schedule    TEXT,
                    status      TEXT,
                    latest_run  JSONB,
                    synced_at   TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (job_id, workspace_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS job_runs (
                    run_id          BIGINT PRIMARY KEY,
                    job_id          BIGINT,
                    workspace_id    TEXT,
                    start_time      TIMESTAMPTZ,
                    end_time        TIMESTAMPTZ,
                    duration_seconds FLOAT,
                    state           TEXT,
                    result_state    TEXT,
                    trigger         TEXT,
                    run_name        TEXT,
                    run_page_url    TEXT,
                    synced_at       TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_runs_job_workspace
                ON job_runs (job_id, workspace_id, start_time DESC)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_sync (
                    workspace_id  TEXT PRIMARY KEY,
                    last_synced_at TIMESTAMPTZ,
                    job_count     INT DEFAULT 0,
                    run_count     INT DEFAULT 0,
                    error         TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_insights_cache (
                    cache_key       TEXT PRIMARY KEY,
                    job_id          BIGINT,
                    workspace_id    TEXT,
                    anomaly_fingerprint TEXT,
                    insight_json    JSONB NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_cache_job_workspace
                ON ai_insights_cache (job_id, workspace_id)
            """)
        logger.info("Lakebase schema initialized")
    except Exception as e:
        logger.error(f"Schema init failed: {e}")


async def upsert_jobs(workspace_id: str, jobs: list) -> None:
    """Upsert a list of JobInfo objects into the jobs table."""
    pool = await get_pool()
    if not pool or not jobs:
        return
    now = datetime.now(timezone.utc)
    records = []
    for j in jobs:
        latest_run_json = None
        if j.latest_run:
            try:
                d = j.latest_run.model_dump(mode="json")
                latest_run_json = json.dumps(d)
            except Exception:
                pass
        records.append((
            j.job_id,
            workspace_id,
            j.name,
            j.creator,
            j.created_time,
            j.schedule,
            j.status,
            latest_run_json,
            now,
        ))
    try:
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO jobs
                    (job_id, workspace_id, name, creator, created_time,
                     schedule, status, latest_run, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                ON CONFLICT (job_id, workspace_id) DO UPDATE SET
                    name        = EXCLUDED.name,
                    creator     = EXCLUDED.creator,
                    schedule    = EXCLUDED.schedule,
                    status      = EXCLUDED.status,
                    latest_run  = EXCLUDED.latest_run,
                    synced_at   = EXCLUDED.synced_at
            """, records)
    except Exception as e:
        logger.error(f"upsert_jobs failed for {workspace_id}: {e}")


async def upsert_runs(workspace_id: str, runs_map: dict) -> int:
    """Upsert job runs from a {job_id: [JobRun]} map. Returns count."""
    pool = await get_pool()
    if not pool:
        return 0
    now = datetime.now(timezone.utc)
    records = []
    for job_id, runs in runs_map.items():
        for r in runs:
            records.append((
                r.run_id,
                r.job_id,
                workspace_id,
                r.start_time,
                r.end_time,
                r.duration_seconds,
                r.state,
                r.result_state,
                r.trigger,
                r.run_name,
                r.run_page_url,
                now,
            ))
    if not records:
        return 0
    try:
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO job_runs
                    (run_id, job_id, workspace_id, start_time, end_time,
                     duration_seconds, state, result_state, trigger,
                     run_name, run_page_url, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (run_id) DO UPDATE SET
                    state            = EXCLUDED.state,
                    end_time         = EXCLUDED.end_time,
                    duration_seconds = EXCLUDED.duration_seconds,
                    result_state     = EXCLUDED.result_state,
                    synced_at        = EXCLUDED.synced_at
            """, records)
        return len(records)
    except Exception as e:
        logger.error(f"upsert_runs failed for {workspace_id}: {e}")
        return 0


async def mark_workspace_synced(
    workspace_id: str,
    job_count: int,
    run_count: int,
    error: Optional[str] = None,
):
    pool = await get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO workspace_sync
                    (workspace_id, last_synced_at, job_count, run_count, error)
                VALUES ($1, NOW(), $2, $3, $4)
                ON CONFLICT (workspace_id) DO UPDATE SET
                    last_synced_at = NOW(),
                    job_count      = $2,
                    run_count      = $3,
                    error          = $4
            """, workspace_id, job_count, run_count, error)
    except Exception as e:
        logger.error(f"mark_workspace_synced failed: {e}")


async def get_jobs_from_db(workspace_id: Optional[str] = None) -> list[dict]:
    """Read cached jobs from Lakebase. Returns [] if DB not available or empty."""
    pool = await get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            if workspace_id:
                rows = await conn.fetch(
                    "SELECT * FROM jobs WHERE workspace_id = $1 ORDER BY name",
                    workspace_id,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM jobs ORDER BY workspace_id, name"
                )
        result = []
        for row in rows:
            d = dict(row)
            # latest_run is stored as JSONB — parse back to dict
            lr = d.pop("latest_run", None)
            if lr:
                if isinstance(lr, str):
                    lr = json.loads(lr)
                d["latest_run"] = lr
            else:
                d["latest_run"] = None
            result.append(d)
        return result
    except Exception as e:
        logger.error(f"get_jobs_from_db failed: {e}")
        return []


async def get_runs_from_db(
    workspace_id: str,
    job_id: int,
    limit: int = 50,
) -> list[dict]:
    """Read cached runs for a specific job from Lakebase."""
    pool = await get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM job_runs
                   WHERE job_id = $1 AND workspace_id = $2
                   ORDER BY start_time DESC LIMIT $3""",
                job_id,
                workspace_id,
                limit,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_runs_from_db failed: {e}")
        return []


async def get_all_runs_from_db(workspace_id: Optional[str] = None, runs_per_job: int = 10) -> dict[int, list[dict]]:
    """Read cached runs grouped by job_id from Lakebase."""
    pool = await get_pool()
    if not pool:
        return {}
    try:
        async with pool.acquire() as conn:
            if workspace_id:
                rows = await conn.fetch(
                    """SELECT DISTINCT ON (job_id) * FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY start_time DESC) AS rn
                        FROM job_runs WHERE workspace_id = $1
                    ) t WHERE rn <= $2 ORDER BY job_id, start_time DESC""",
                    workspace_id,
                    runs_per_job,
                )
            else:
                rows = await conn.fetch(
                    """SELECT * FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY job_id, workspace_id ORDER BY start_time DESC) AS rn
                        FROM job_runs
                    ) t WHERE rn <= $1 ORDER BY job_id, start_time DESC""",
                    runs_per_job,
                )
        result: dict[int, list[dict]] = {}
        for row in rows:
            d = dict(row)
            d.pop("rn", None)
            jid = d["job_id"]
            result.setdefault(jid, []).append(d)
        return result
    except Exception as e:
        logger.error(f"get_all_runs_from_db failed: {e}")
        return {}


async def get_sync_status() -> list[dict]:
    """Return last-sync metadata per workspace."""
    pool = await get_pool()
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM workspace_sync ORDER BY workspace_id"
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_sync_status failed: {e}")
        return []


async def is_cache_fresh(workspace_id: str, max_age_seconds: int = 180) -> bool:
    """True if the cache for this workspace was synced within max_age_seconds."""
    pool = await get_pool()
    if not pool:
        return False
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT last_synced_at FROM workspace_sync
                   WHERE workspace_id = $1
                     AND last_synced_at > NOW() - INTERVAL '1 second' * $2""",
                workspace_id,
                max_age_seconds,
            )
        return row is not None
    except Exception as e:
        logger.error(f"is_cache_fresh check failed: {e}")
        return False


# ── AI Insights Cache ──────────────────────────────────────────────────────

async def get_cached_insight(cache_key: str, max_age_seconds: int = 86400) -> Optional[dict]:
    """Return a cached AI insight if it exists and is fresher than max_age_seconds (default 24h)."""
    pool = await get_pool()
    if not pool:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT insight_json FROM ai_insights_cache
                   WHERE cache_key = $1
                     AND created_at > NOW() - INTERVAL '1 second' * $2""",
                cache_key,
                max_age_seconds,
            )
        if row:
            insight = row["insight_json"]
            if isinstance(insight, str):
                return json.loads(insight)
            return dict(insight) if insight else None
        return None
    except Exception as e:
        logger.error(f"get_cached_insight failed for {cache_key}: {e}")
        return None


async def store_insight(
    cache_key: str,
    job_id: int,
    workspace_id: str,
    anomaly_fingerprint: str,
    insight: dict,
) -> None:
    """Store an AI insight in the Lakebase cache."""
    pool = await get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO ai_insights_cache
                       (cache_key, job_id, workspace_id, anomaly_fingerprint, insight_json, created_at)
                   VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
                   ON CONFLICT (cache_key) DO UPDATE SET
                       insight_json = EXCLUDED.insight_json,
                       created_at   = NOW()""",
                cache_key,
                job_id,
                workspace_id,
                anomaly_fingerprint,
                json.dumps(insight),
            )
    except Exception as e:
        logger.error(f"store_insight failed for {cache_key}: {e}")
